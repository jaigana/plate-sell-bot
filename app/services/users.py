from __future__ import annotations

from dataclasses import dataclass

from app.services.common import Repositories, Service


@dataclass(frozen=True, slots=True)
class TelegramUserData:
    telegram_id: int
    username: str | None
    first_name: str
    last_name: str | None


class UserService(Service):
    async def ensure(self, user: TelegramUserData) -> dict:
        async with self.pool.acquire() as conn, conn.transaction():
            row = await self.repos.users.ensure(conn, user.telegram_id, user.username, user.first_name, user.last_name)
            return dict(row)

    async def profile(self, user_id: int) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await self.repos.users.get(conn, user_id)
            return dict(row) if row else None

