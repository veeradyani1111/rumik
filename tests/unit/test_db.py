from pathlib import Path

import pytest

from sdk.server.db import Database


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append((query, args))
        return "UPDATE 1"

    async def fetchval(self, query: str, *args: object):
        self.executed.append((query, args))
        if "INSERT INTO accounts" in query:
            return "account-id"
        if "SELECT account_id" in query:
            return "account-id"
        return "key-id"


class AcquireContext:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> FakeConnection:
        return self.connection

    async def __aexit__(self, *_args) -> None:
        return None


class FakePool:
    def __init__(self) -> None:
        self.connection = FakeConnection()
        self.closed = False

    def acquire(self) -> AcquireContext:
        return AcquireContext(self.connection)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_connect_applies_schema_and_close_releases_pool() -> None:
    pool = FakePool()

    async def create_pool(_url: str):
        return pool

    database = Database("postgresql://test", pool_factory=create_pool)
    await database.connect()
    await database.close()

    schema_query = pool.connection.executed[0][0]
    assert "CREATE TABLE IF NOT EXISTS accounts" in schema_query
    assert "CREATE TABLE IF NOT EXISTS kyc_results" in schema_query
    assert pool.closed is True


@pytest.mark.asyncio
async def test_account_repository_queries_use_hashes_and_return_account() -> None:
    pool = FakePool()

    async def create_pool(_url: str):
        return pool

    database = Database("postgresql://test", pool_factory=create_pool)
    await database.connect()

    account_id = await database.get_or_create_account("dev@example.com")
    await database.create_api_key(account_id, "sha256-value", "default")
    resolved = await database.resolve_api_key("sha256-value")
    revoked = await database.revoke_api_key(account_id, "sha256-value")

    all_queries = "\n".join(query for query, _args in pool.connection.executed)
    all_args = [arg for _query, args in pool.connection.executed for arg in args]
    assert resolved == "account-id"
    assert revoked is True
    assert "key_hash" in all_queries
    assert "sha256-value" in all_args
    assert not any(str(arg).startswith("rk_live_") for arg in all_args)


def test_schema_file_is_next_to_database_adapter() -> None:
    assert Path("sdk/server/schema.sql").is_file()
