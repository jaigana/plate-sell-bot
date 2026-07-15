from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from app.services.common import Service

logger = logging.getLogger(__name__)


class NotificationService(Service):
    async def deliver_due(self, bot: Bot) -> int:
        delivered = 0
        async with self.pool.acquire() as conn, conn.transaction():
            notifications = await self.repos.notifications.due(conn)
            for notification in notifications:
                text = self._text(notification["notification_type"], notification["payload"])
                try:
                    await bot.send_message(notification["user_id"], text)
                except TelegramAPIError as exc:
                    logger.warning("notification_delivery_failed", extra={"notification_id": notification["id"], "error": str(exc)})
                    await self.repos.notifications.failed(conn, notification["id"], str(exc))
                else:
                    await self.repos.notifications.delivered(conn, notification["id"])
                    delivered += 1
        return delivered

    @staticmethod
    def _text(kind: str, payload: dict) -> str:
        templates = {
            "AUCTION_WON": "🏆 Вы выиграли аукцион: {plate_number} за ⭐{amount}.",
            "AUCTION_OUTBID": "🔔 Вашу ставку перебили. Новая ставка: ⭐{amount}.",
            "AUCTION_FINISHED": "🔨 Аукцион завершён: {plate_number}.",
            "SALE_COMPLETED": "✅ Номер {plate_number} продан. Вам начислено ⭐{amount}.",
            "PLATE_PURCHASED": "✅ Номер {plate_number} теперь в вашей коллекции.",
            "BALANCE_TOPUP": "⭐ Баланс пополнен на ⭐{amount}.",
            "ACCOUNT_INACTIVE_WARNING": "⚠️ Аккаунт неактивен. Войдите в бот, чтобы сохранить игровые номера.",
        }
        template = templates.get(kind, "Новое уведомление CPM2 Plates Market.")
        try:
            return template.format(**payload)
        except KeyError:
            return template
