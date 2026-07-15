from __future__ import annotations

from typing import Any

import asyncpg


class SettingsRepository:
    async def get(self, conn: asyncpg.Connection, key: str) -> Any:
        value = await conn.fetchval("SELECT value FROM platform_settings WHERE key=$1", key)
        if value is None:
            raise KeyError(key)
        return value

    async def all(self, conn: asyncpg.Connection) -> dict[str, Any]:
        return {row["key"]: row["value"] for row in await conn.fetch("SELECT key,value FROM platform_settings")}

    async def set(self, conn: asyncpg.Connection, key: str, value: Any, actor_id: int) -> None:
        await conn.execute(
            """INSERT INTO platform_settings(key,value,updated_by) VALUES($1,$2::jsonb,$3)
            ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value,updated_by=EXCLUDED.updated_by,updated_at=now()""",
            key, value, actor_id,
        )

    async def kz_blacklist(self, conn: asyncpg.Connection) -> set[str]:
        return {row["series"] for row in await conn.fetch("SELECT series FROM blacklisted_series WHERE country_code='KZ'")}

    async def add_blacklist(self, conn: asyncpg.Connection, country_code: str, series: str, actor_id: int) -> None:
        await conn.execute(
            """INSERT INTO blacklisted_series(country_code,series,created_by) VALUES($1,$2,$3)
            ON CONFLICT(country_code,series) DO NOTHING""", country_code, series, actor_id
        )

    async def remove_blacklist(self, conn: asyncpg.Connection, country_code: str, series: str) -> None:
        await conn.execute("DELETE FROM blacklisted_series WHERE country_code=$1 AND series=$2", country_code, series)

