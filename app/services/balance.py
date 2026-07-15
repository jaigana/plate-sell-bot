from __future__ import annotations

import logging

from app.domain import DomainError, NotFoundError
from app.services.common import Service

logger = logging.getLogger(__name__)


class BalanceService(Service):
    async def top_up(self, user_id: int, amount: int, telegram_charge_id: str) -> bool:
        if amount < 1:
            raise DomainError("Сумма пополнения должна быть положительной.")
        async with self.pool.acquire() as conn, conn.transaction():
            existing = await self.repos.transactions.get_by_external_ref(conn, telegram_charge_id)
            if existing:
                return False
            users = await self.repos.users.lock_many(conn, [user_id])
            user = users.get(user_id)
            if not user:
                raise NotFoundError("Пользователь не найден.")
            await self.repos.users.set_balances(conn, user_id, user["balance_available"] + amount, user["balance_frozen"])
            await self.repos.transactions.create(
                conn, user_id=user_id, counterparty_id=None, plate_id=None, amount=amount,
                transaction_type="TOPUP", external_ref=telegram_charge_id, metadata={"source": "telegram_stars"},
            )
            await self.repos.notifications.enqueue(conn, user_id, "BALANCE_TOPUP", {"amount": amount})
            logger.info("balance_topped_up", extra={"user_id": user_id, "amount": amount})
            return True

    async def adjust(self, user_id: int, amount: int, reason: str, actor_id: int) -> dict:
        if amount == 0:
            raise DomainError("Изменение баланса не может быть нулевым.")
        async with self.pool.acquire() as conn, conn.transaction():
            users = await self.repos.users.lock_many(conn, [user_id])
            user = users.get(user_id)
            if not user:
                raise NotFoundError("Пользователь не найден.")
            available = user["balance_available"] + amount
            if available < 0:
                raise DomainError("Нельзя списать больше доступного баланса.")
            await self.repos.users.set_balances(conn, user_id, available, user["balance_frozen"])
            await self.repos.transactions.create(
                conn, user_id=user_id, counterparty_id=actor_id, plate_id=None, amount=amount,
                transaction_type="ADMIN_ADJUSTMENT", metadata={"reason": reason},
            )
            await self.repos.admin.audit(conn, actor_id, "balance_adjust", "user", str(user_id), {"amount": amount, "reason": reason})
            logger.info("balance_adjusted", extra={"user_id": user_id, "actor_id": actor_id, "amount": amount})
            return {"available": available, "frozen": user["balance_frozen"]}
