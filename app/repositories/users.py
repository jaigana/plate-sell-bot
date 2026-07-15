from __future__ import annotations

from typing import Any

import asyncpg


class UserRepository:
    async def ensure(
        self, conn: asyncpg.Connection, telegram_id: int, username: str | None, first_name: str, last_name: str | None
    ) -> asyncpg.Record:
        return await conn.fetchrow(
            """
            INSERT INTO users(telegram_id, username, first_name, last_name)
            VALUES($1, $2, $3, $4)
            ON CONFLICT (telegram_id) DO UPDATE SET
                username = EXCLUDED.username, first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name, last_activity = now(), updated_at = now()
            RETURNING *
            """,
            telegram_id, username, first_name, last_name,
        )

    async def get(self, conn: asyncpg.Connection, telegram_id: int) -> asyncpg.Record | None:
        return await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)

    async def lock_many(self, conn: asyncpg.Connection, user_ids: list[int]) -> dict[int, asyncpg.Record]:
        if not user_ids:
            return {}
        rows = await conn.fetch(
            "SELECT * FROM users WHERE telegram_id = ANY($1::bigint[]) ORDER BY telegram_id FOR UPDATE", user_ids
        )
        return {row["telegram_id"]: row for row in rows}

    async def set_balances(self, conn: asyncpg.Connection, telegram_id: int, available: int, frozen: int) -> None:
        await conn.execute(
            """
            UPDATE users SET balance_available=$2, balance_frozen=$3, updated_at=now(), last_activity=now()
            WHERE telegram_id=$1
            """,
            telegram_id, available, frozen,
        )

    async def list_inactive(self, conn: asyncpg.Connection, days: int, warning_days: int) -> tuple[list[asyncpg.Record], list[asyncpg.Record]]:
        inactive = await conn.fetch(
            "SELECT * FROM users WHERE NOT is_blocked AND last_activity < now() - ($1::text || ' days')::interval",
            str(days),
        )
        warnings = await conn.fetch(
            """
            SELECT * FROM users WHERE NOT is_blocked
              AND last_activity < now() - ($1::text || ' days')::interval
              AND last_activity >= now() - ($2::text || ' days')::interval
            """,
            str(days - warning_days), str(days),
        )
        return list(inactive), list(warnings)

