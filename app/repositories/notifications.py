from __future__ import annotations

from typing import Any

import asyncpg


class NotificationRepository:
    async def enqueue(self, conn: asyncpg.Connection, user_id: int, notification_type: str, payload: dict[str, Any]) -> None:
        await conn.execute(
            "INSERT INTO notifications(user_id,notification_type,payload) VALUES($1,$2,$3::jsonb)", user_id, notification_type, payload
        )

    async def due(self, conn: asyncpg.Connection, limit: int = 50) -> list[asyncpg.Record]:
        return list(await conn.fetch(
            """SELECT * FROM notifications WHERE delivered_at IS NULL AND next_attempt_at <= now()
            ORDER BY id FOR UPDATE SKIP LOCKED LIMIT $1""", limit
        ))

    async def delivered(self, conn: asyncpg.Connection, notification_id: int) -> None:
        await conn.execute("UPDATE notifications SET delivered_at=now(), attempts=attempts+1,last_error=NULL WHERE id=$1", notification_id)

    async def failed(self, conn: asyncpg.Connection, notification_id: int, error: str) -> None:
        await conn.execute(
            """UPDATE notifications SET attempts=attempts+1,last_error=$2,
            next_attempt_at=now() + (LEAST(60, power(2, attempts + 1))::text || ' minutes')::interval WHERE id=$1""",
            notification_id, error[:500],
        )

