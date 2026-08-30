from __future__ import annotations

from collections.abc import Awaitable, Callable
import json
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

    async def create_session(self, *, session_id: str, account_id: str, mode: str) -> None:
        query = """
            INSERT INTO sessions (id, account_id, mode, status)
            VALUES ($1, $2::uuid, $3, 'active')
        """
        async with self._require_pool().acquire() as connection:
            await connection.execute(query, session_id, account_id, mode)

    async def finish_session(
        self, session_id: str, *, status: str, turns: int = 0, images_sent: int = 0
    ) -> None:
        query = """
            UPDATE sessions
            SET status = $2, ended_at = now(), turns = $3, images_sent = $4
            WHERE id = $1
        """
        async with self._require_pool().acquire() as connection:
            await connection.execute(query, session_id, status, turns, images_sent)

    async def save_kyc_result(
        self,
        *,
        account_id: str,
        session_id: str,
        decision: str,
        checks: dict,
        extracted: dict,
        notes: str,
    ) -> str:
        result_id = uuid4()
        query = """
            INSERT INTO kyc_results
                (id, account_id, session_id, decision, checks, extracted, notes)
            VALUES ($1, $2::uuid, $3, $4, $5::jsonb, $6::jsonb, $7)
            RETURNING id
        """
        async with self._require_pool().acquire() as connection:
            value = await connection.fetchval(
                query,
                result_id,
                account_id,
                session_id,
                decision,
                json.dumps(checks),
                json.dumps(extracted),
                notes,
            )
        return str(value or result_id)

    async def account_summary(self, account_id: str) -> dict:
        query = """
            SELECT
                a.email,
                COALESCE(
                    jsonb_agg(
                        jsonb_build_object(
                            'id', k.id,
                            'label', k.label,
                            'masked', 'rk_live_••••',
                            'created_at', k.created_at,
                            'revoked', k.revoked_at IS NOT NULL
                        ) ORDER BY k.created_at DESC
                    ) FILTER (WHERE k.id IS NOT NULL),
                    '[]'::jsonb
                ) AS keys,
                (SELECT count(*) FROM sessions s WHERE s.account_id = a.id) AS session_count,
                (SELECT count(*) FROM kyc_results r WHERE r.account_id = a.id) AS kyc_count
            FROM accounts a
            LEFT JOIN api_keys k ON k.account_id = a.id
            WHERE a.id = $1::uuid
            GROUP BY a.id, a.email
        """
        async with self._require_pool().acquire() as connection:
            row = await connection.fetchrow(query, account_id)
        if row is None:
            raise LookupError("Account not found")
        summary = dict(row)
        if isinstance(summary.get("keys"), str):
            summary["keys"] = json.loads(summary["keys"])
        return summary

    async def ensure_demo_key(self, email: str, key_hash: str) -> str:
        account_id = await self.get_or_create_account(email)
        query = """
            INSERT INTO api_keys (id, account_id, key_hash, label)
            VALUES ($1, $2::uuid, $3, 'demo')
            ON CONFLICT (key_hash) DO UPDATE
            SET revoked_at = NULL
        """
        async with self._require_pool().acquire() as connection:
            await connection.execute(query, uuid4(), account_id, key_hash)
        return account_id
