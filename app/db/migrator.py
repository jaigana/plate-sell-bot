from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)


async def apply_migrations(pool: asyncpg.Pool, migrations_dir: Path) -> None:
    """Apply immutable, name-ordered SQL files exactly once."""
    files = sorted(path for path in migrations_dir.glob("*.sql") if path.is_file())
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id BIGSERIAL PRIMARY KEY,
                filename TEXT UNIQUE NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        applied = {row["filename"] for row in await conn.fetch("SELECT filename FROM schema_migrations")}
        for path in files:
            if path.name in applied:
                continue
            sql = path.read_text(encoding="utf-8")
            # ``filename`` is a built-in LogRecord field; structured extras must
            # never overwrite it or logging raises KeyError during startup.
            logger.info("applying_migration", extra={"migration_filename": path.name})
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute("INSERT INTO schema_migrations(filename) VALUES($1)", path.name)
