from dataclasses import dataclass

import pytest

from sdk.server.accounts import AccountService, hash_api_key


@dataclass
class StoredKey:
    account_id: str
    key_hash: str
    revoked: bool = False


class FakeAccountRepository:
    def __init__(self) -> None:
        self.accounts_by_email: dict[str, str] = {}
        self.keys: list[StoredKey] = []

    async def get_or_create_account(self, email: str) -> str:
        self.accounts_by_email.setdefault(email, f"account-{len(self.accounts_by_email) + 1}")
        return self.accounts_by_email[email]

    async def create_api_key(self, account_id: str, key_hash: str, label: str) -> str:
        self.keys.append(StoredKey(account_id, key_hash))
        return f"key-{len(self.keys)}"

    async def resolve_api_key(self, key_hash: str) -> str | None:
        return next(
            (key.account_id for key in self.keys if key.key_hash == key_hash and not key.revoked),
            None,
        )

    async def revoke_api_key(self, account_id: str, key_hash: str) -> bool:
        for key in self.keys:
            if key.account_id == account_id and key.key_hash == key_hash and not key.revoked:
                key.revoked = True
                return True
        return False


@pytest.mark.asyncio
async def test_signup_issues_plaintext_once_and_stores_only_sha256() -> None:
    repository = FakeAccountRepository()
    service = AccountService(repository)

    issued = await service.signup("Dev@Example.com")

    assert issued.api_key.startswith("rk_live_")
    assert len(issued.api_key.removeprefix("rk_live_")) == 32
    assert repository.accounts_by_email == {"dev@example.com": issued.account_id}
    assert repository.keys[0].key_hash == hash_api_key(issued.api_key)
    assert issued.api_key not in repr(repository.keys)


@pytest.mark.asyncio
async def test_returning_email_gets_a_fresh_key_for_the_same_account() -> None:
    repository = FakeAccountRepository()
    service = AccountService(repository)

    first = await service.signup("dev@example.com")
    second = await service.signup("DEV@example.com")

    assert first.account_id == second.account_id
    assert first.api_key != second.api_key
    assert len(repository.keys) == 2


@pytest.mark.asyncio
async def test_validate_accepts_good_key_and_rejects_unknown_or_revoked_key() -> None:
    repository = FakeAccountRepository()
    service = AccountService(repository)
    issued = await service.signup("dev@example.com")

    assert await service.validate(issued.api_key) == issued.account_id
    assert await service.validate("rk_live_unknown") is None
    assert await service.revoke(issued.account_id, issued.api_key) is True
    assert await service.validate(issued.api_key) is None


@pytest.mark.asyncio
async def test_signup_rejects_invalid_email() -> None:
    service = AccountService(FakeAccountRepository())

    with pytest.raises(ValueError, match="valid email"):
        await service.signup("not-an-email")


@pytest.mark.asyncio
async def test_regenerate_issues_an_additional_key_for_authenticated_account() -> None:
    repository = FakeAccountRepository()
    service = AccountService(repository)
    issued = await service.signup("dev@example.com")

    regenerated = await service.regenerate(issued.account_id)

    assert regenerated.account_id == issued.account_id
    assert regenerated.api_key != issued.api_key
    assert len(repository.keys) == 2
