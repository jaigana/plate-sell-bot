from __future__ import annotations

from typing import Any

import asyncpg


class AdminRepository:
    async def is_admin(self, conn: asyncpg.Connection, user_id: int) -> bool:
        return bool(await conn.fetchval("SELECT EXISTS(SELECT 1 FROM admins WHERE user_id=$1)", user_id))

    async def grant(self, conn: asyncpg.Connection, user_id: int, actor_id: int) -> None:
        await conn.execute(
            "INSERT INTO admins(user_id,granted_by) VALUES($1,$2) ON CONFLICT(user_id) DO NOTHING", user_id, actor_id
        )

    async def block(self, conn: asyncpg.Connection, user_id: int, actor_id: int, reason: str) -> None:
        await conn.execute("UPDATE users SET is_blocked=TRUE,updated_at=now() WHERE telegram_id=$1", user_id)
        await conn.execute(
            """INSERT INTO user_blocks(user_id,blocked_by,reason) VALUES($1,$2,$3)
            ON CONFLICT(user_id) DO UPDATE SET blocked_by=EXCLUDED.blocked_by,reason=EXCLUDED.reason,created_at=now()""",
            user_id, actor_id, reason,
        )

    async def unblock(self, conn: asyncpg.Connection, user_id: int) -> None:
        await conn.execute("UPDATE users SET is_blocked=FALSE,updated_at=now() WHERE telegram_id=$1", user_id)
        await conn.execute("DELETE FROM user_blocks WHERE user_id=$1", user_id)

    async def stats(self, conn: asyncpg.Connection) -> dict[str, int]:
        row = await conn.fetchrow(
            """SELECT (SELECT count(*) FROM users)::int AS users, (SELECT count(*) FROM plates)::int AS plates,
            (SELECT count(*) FROM sales WHERE status='ACTIVE')::int AS sales,
            (SELECT count(*) FROM auctions WHERE status='ACTIVE')::int AS auctions,
            (SELECT coalesce(sum(balance_available + balance_frozen),0) FROM users)::bigint AS stars"""
        )
        return dict(row)

    async def audit(self, conn: asyncpg.Connection, actor_id: int, action: str, entity_type: str, entity_id: str, metadata: dict[str, Any]) -> None:
        await conn.execute(
            """INSERT INTO audit_logs(actor_id,action,entity_type,entity_id,metadata)
            VALUES($1,$2,$3,$4,$5::jsonb)""", actor_id, action, entity_type, entity_id, metadata
        )
