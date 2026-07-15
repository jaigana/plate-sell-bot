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

    async def official_forbidden_series(self, conn: asyncpg.Connection, country_code: str) -> set[str]:
        rows = await conn.fetch(
            "SELECT series FROM official_forbidden_plate_series WHERE country_code=$1", country_code.upper()
        )
        return {row["series"] for row in rows}
