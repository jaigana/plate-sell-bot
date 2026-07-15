from __future__ import annotations

import asyncpg


class BackupRepository:
    async def started(self, conn: asyncpg.Connection, requested_by: int | None, filename: str) -> asyncpg.Record:
        return await conn.fetchrow(
            "INSERT INTO backups(requested_by,filename,status) VALUES($1,$2,'STARTED') RETURNING *", requested_by, filename
        )

    async def complete(self, conn: asyncpg.Connection, backup_id: int) -> None:
        await conn.execute("UPDATE backups SET status='SENT',completed_at=now() WHERE id=$1", backup_id)

    async def fail(self, conn: asyncpg.Connection, backup_id: int, error: str) -> None:
        await conn.execute("UPDATE backups SET status='FAILED',error=$2,completed_at=now() WHERE id=$1", backup_id, error[:500])
