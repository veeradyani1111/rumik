from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from typing import Protocol


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class AccountRepository(Protocol):
    async def get_or_create_account(self, email: str) -> str: ...

    async def create_api_key(self, account_id: str, key_hash: str, label: str) -> str: ...

    async def resolve_api_key(self, key_hash: str) -> str | None: ...

    async def revoke_api_key(self, account_id: str, key_hash: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class IssuedKey:
    account_id: str
    api_key: str


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def mint_api_key() -> str:
    return f"rk_live_{secrets.token_urlsafe(24)}"


class AccountService:
    def __init__(self, repository: AccountRepository) -> None:
        self._repository = repository

    async def signup(self, email: str, *, label: str = "default") -> IssuedKey:
        normalized_email = email.strip().lower()
        if EMAIL_PATTERN.fullmatch(normalized_email) is None:
            raise ValueError("Enter a valid email address")
        account_id = await self._repository.get_or_create_account(normalized_email)
        plaintext = mint_api_key()
        await self._repository.create_api_key(account_id, hash_api_key(plaintext), label)
        return IssuedKey(account_id=account_id, api_key=plaintext)

    async def validate(self, api_key: str) -> str | None:
        if not api_key:
            return None
        return await self._repository.resolve_api_key(hash_api_key(api_key))

    async def revoke(self, account_id: str, api_key: str) -> bool:
        return await self._repository.revoke_api_key(account_id, hash_api_key(api_key))
