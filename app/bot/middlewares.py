from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.services.users import TelegramUserData, UserService

logger = logging.getLogger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self, interval_seconds: float = 0.5) -> None:
        self.interval_seconds = interval_seconds
        self._last_seen: dict[int, float] = {}

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any:
        from_user = data.get("event_from_user")
        if not from_user:
            return await handler(event, data)
        now = time.monotonic()
        previous = self._last_seen.get(from_user.id, 0.0)
        self._last_seen[from_user.id] = now
        if now - previous < self.interval_seconds:
            if isinstance(event, CallbackQuery):
                await event.answer("Слишком быстро. Попробуйте через мгновение.", show_alert=False)
            return None
        return await handler(event, data)


class UserActivityMiddleware(BaseMiddleware):
    def __init__(self, users: UserService) -> None:
        self.users = users

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: TelegramObject, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        if user:
            try:
                await self.users.ensure(TelegramUserData(user.id, user.username, user.first_name or "", user.last_name))
            except Exception:
                logger.exception("user_activity_record_failed", extra={"user_id": user.id})
                raise
        return await handler(event, data)
