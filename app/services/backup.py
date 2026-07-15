from __future__ import annotations

import asyncio
import gzip
import logging
from datetime import datetime, timezone
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

from app.services.common import Service

logger = logging.getLogger(__name__)


class BackupService(Service):
    def __init__(self, pool, repositories, database_url: str, owner_id: int) -> None:
        super().__init__(pool, repositories)
        self.database_url = database_url
        self.owner_id = owner_id

    async def create_and_send(self, bot: Bot, requested_by: int | None = None) -> None:
        backup_dir = Path("backups")
        backup_dir.mkdir(exist_ok=True)
        name = f"backup_{datetime.now(timezone.utc):%Y_%m_%d}.sql"
        path = backup_dir / name
        async with self.pool.acquire() as conn, conn.transaction():
            row = await self.repos.backups.started(conn, requested_by, name)
        try:
            process = await asyncio.create_subprocess_exec(
                "pg_dump", "--no-owner", "--format=plain", f"--dbname={self.database_url}",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            if process.returncode != 0:
                raise RuntimeError(stderr.decode("utf-8", "replace"))
            path.write_bytes(stdout)
            send_path = path
            if path.stat().st_size > 48 * 1024 * 1024:
                send_path = path.with_suffix(".sql.gz")
                with path.open("rb") as source, gzip.open(send_path, "wb") as target:
                    target.writelines(source)
            if send_path.stat().st_size > 50 * 1024 * 1024:
                await bot.send_message(self.owner_id, "Резервная копия превышает лимит Telegram. Используйте Railway CLI для pg_dump.")
            else:
                await bot.send_document(self.owner_id, FSInputFile(send_path), caption="Резервная копия PostgreSQL CPM2 Plates Market")
            async with self.pool.acquire() as conn, conn.transaction():
                await self.repos.backups.complete(conn, row["id"])
        except Exception as exc:
            logger.exception("backup_failed")
            async with self.pool.acquire() as conn, conn.transaction():
                await self.repos.backups.fail(conn, row["id"], str(exc))
            await bot.send_message(self.owner_id, "Не удалось создать резервную копию. Проверьте логи Railway.")
            raise
        finally:
            for candidate in (path, path.with_suffix(".sql.gz")):
                candidate.unlink(missing_ok=True)
