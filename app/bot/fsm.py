from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import asyncpg
from aiogram.fsm.state import State
from aiogram.fsm.storage.base import BaseStorage, StorageKey


class PgStorage(BaseStorage):
    """aiogram FSM storage backed only by PostgreSQL."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self.pool = pool

    @staticmethod
    def _parts(key: StorageKey) -> tuple[int, int, int, int, str, str]:
        return (
            key.bot_id, key.chat_id, key.user_id, key.thread_id or 0,
            key.business_connection_id or "", key.destiny,
        )

    async def set_state(self, key: StorageKey, state: str | State | None = None) -> None:
        value = state.state if isinstance(state, State) else state
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_sessions(bot_id,chat_id,user_id,thread_id,business_connection_id,destiny,fsm_state)
                VALUES($1,$2,$3,$4,$5,$6,$7)
                ON CONFLICT(bot_id,chat_id,user_id,thread_id,business_connection_id,destiny)
                DO UPDATE SET fsm_state=EXCLUDED.fsm_state,updated_at=now()
                """, *self._parts(key), value,
            )

    async def get_state(self, key: StorageKey) -> str | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                """SELECT fsm_state FROM user_sessions WHERE bot_id=$1 AND chat_id=$2 AND user_id=$3
                AND thread_id=$4 AND business_connection_id=$5 AND destiny=$6""", *self._parts(key)
            )

    async def set_data(self, key: StorageKey, data: Mapping[str, Any]) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_sessions(bot_id,chat_id,user_id,thread_id,business_connection_id,destiny,fsm_data)
                VALUES($1,$2,$3,$4,$5,$6,$7::jsonb)
                ON CONFLICT(bot_id,chat_id,user_id,thread_id,business_connection_id,destiny)
                DO UPDATE SET fsm_data=EXCLUDED.fsm_data,updated_at=now()
                """, *self._parts(key), dict(data),
            )

    async def get_data(self, key: StorageKey) -> dict[str, Any]:
        async with self.pool.acquire() as conn:
            data = await conn.fetchval(
                """SELECT fsm_data FROM user_sessions WHERE bot_id=$1 AND chat_id=$2 AND user_id=$3
                AND thread_id=$4 AND business_connection_id=$5 AND destiny=$6""", *self._parts(key)
            )
            return dict(data or {})

    async def push_screen(self, key: StorageKey, screen: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_sessions(bot_id,chat_id,user_id,thread_id,business_connection_id,destiny,screen_stack)
                VALUES($1,$2,$3,$4,$5,$6,jsonb_build_array($7::text))
                ON CONFLICT(bot_id,chat_id,user_id,thread_id,business_connection_id,destiny)
                DO UPDATE SET screen_stack=user_sessions.screen_stack || jsonb_build_array($7::text),updated_at=now()
                """, *self._parts(key), screen,
            )

    async def pop_screen(self, key: StorageKey) -> str | None:
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                """SELECT screen_stack FROM user_sessions WHERE bot_id=$1 AND chat_id=$2 AND user_id=$3
                AND thread_id=$4 AND business_connection_id=$5 AND destiny=$6 FOR UPDATE""", *self._parts(key)
            )
            if not row or not row["screen_stack"]:
                return None
            stack = list(row["screen_stack"])
            value = stack.pop()
            await conn.execute(
                """UPDATE user_sessions SET screen_stack=$7::jsonb,updated_at=now() WHERE bot_id=$1 AND chat_id=$2
                AND user_id=$3 AND thread_id=$4 AND business_connection_id=$5 AND destiny=$6""", *self._parts(key), stack
            )
            return value

    async def close(self) -> None:
        # The application owns the pool lifecycle.
        return None
