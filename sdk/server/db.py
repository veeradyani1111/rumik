from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

import asyncpg


PoolFactory = Callable[[str], Awaitable[Any]]


class Database:
    def __init__(self, database_url: str, *, pool_factory: PoolFactory = asyncpg.create_pool) -> None:
        self._database_url = database_url
        self._pool_factory = pool_factory
        self._pool: Any | None = None

    async def connect(self) -> None:
        if not self._database_url:
            raise RuntimeError("DATABASE_URL is required to start the platform server")
        self._pool = await self._pool_factory(self._database_url)
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        async with self._pool.acquire() as connection:
            await connection.execute(schema)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _require_pool(self):
        if self._pool is None:
            raise RuntimeError("Database.connect() must be called first")
        return self._pool

    async def get_or_create_account(self, email: str) -> str:
        query = """
            INSERT INTO accounts (id, email) VALUES ($1, $2)
            ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
            RETURNING id
        """
        async with self._require_pool().acquire() as connection:
            value = await connection.fetchval(query, uuid4(), email)
        return str(value)

    async def create_api_key(self, account_id: str, key_hash: str, label: str) -> str:
        query = """
            INSERT INTO api_keys (id, account_id, key_hash, label)
            VALUES ($1, $2::uuid, $3, $4)
            RETURNING id
        """
        async with self._require_pool().acquire() as connection:
            value = await connection.fetchval(query, uuid4(), account_id, key_hash, label)
        return str(value)

    async def resolve_api_key(self, key_hash: str) -> str | None:
        query = """
            SELECT account_id FROM api_keys
            WHERE key_hash = $1 AND revoked_at IS NULL
        """
        async with self._require_pool().acquire() as connection:
            value = await connection.fetchval(query, key_hash)
        return str(value) if value is not None else None

    async def revoke_api_key(self, account_id: str, key_hash: str) -> bool:
        query = """
            UPDATE api_keys SET revoked_at = now()
            WHERE account_id = $1::uuid AND key_hash = $2 AND revoked_at IS NULL
        """
        async with self._require_pool().acquire() as connection:
            status = await connection.execute(query, account_id, key_hash)
        return status.endswith(" 1")
