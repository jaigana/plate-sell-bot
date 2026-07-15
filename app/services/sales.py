from __future__ import annotations

import logging

from app.domain import DomainError, NotFoundError, PlateState, split_sale_amount
from app.services.common import Service, setting_int

logger = logging.getLogger(__name__)


class SaleService(Service):
    async def create(self, seller_id: int, plate_id: int, price: int) -> dict:
        if not 1 <= price <= 99_999:
            raise DomainError("Цена должна быть целым числом от ⭐1 до ⭐99 999.")
        async with self.pool.acquire() as conn, conn.transaction():
            plate = await self.repos.plates.lock(conn, plate_id)
            if not plate:
                raise NotFoundError("Номер не найден.")
            if plate["owner_id"] != seller_id or plate["state"] != PlateState.OWNED:
                raise DomainError("Можно продавать только свой свободный номер.")
            if plate["reserved_until"] and await conn.fetchval("SELECT $1 > now()", plate["reserved_until"]):
                raise DomainError("Номер временно зарезервирован.")
            sale = await self.repos.sales.create(conn, plate_id, seller_id, price)
            await self.repos.plates.set_owner_and_state(conn, plate_id, seller_id, PlateState.FIXED_SALE)
            return dict(sale)

    async def buy(self, buyer_id: int, plate_id: int) -> dict:
        async with self.pool.acquire() as conn, conn.transaction():
            plate = await self.repos.plates.lock(conn, plate_id)
            if not plate or plate["state"] != PlateState.FIXED_SALE:
                raise DomainError("Этот номер больше не продаётся по фиксированной цене.")
            sale = await self.repos.sales.lock_active_by_plate(conn, plate_id)
            if not sale:
                raise DomainError("Активная продажа не найдена.")
            seller_id = sale["seller_id"]
            if buyer_id == seller_id:
                raise DomainError("Нельзя купить собственный номер.")
            users = await self.repos.users.lock_many(conn, [buyer_id, seller_id])
            buyer, seller = users.get(buyer_id), users.get(seller_id)
            if not buyer or not seller:
                raise NotFoundError("Участник сделки не найден.")
            if buyer["is_blocked"]:
                raise DomainError("Ваш аккаунт заблокирован.")
            price = sale["price"]
            if buyer["balance_available"] < price:
                raise DomainError("Недостаточно доступных ⭐. Пополните баланс.")
            commission = await setting_int(conn, self.repos, "commission_percent")
            split = split_sale_amount(price, commission)
            await self.repos.users.set_balances(conn, buyer_id, buyer["balance_available"] - price, buyer["balance_frozen"])
            await self.repos.users.set_balances(conn, seller_id, seller["balance_available"] + split.seller_amount, seller["balance_frozen"])
            await self.repos.sales.complete(conn, sale["id"], buyer_id)
            await self.repos.plates.set_owner_and_state(conn, plate_id, buyer_id, PlateState.OWNED)
            await self.repos.transactions.create(
                conn, user_id=buyer_id, counterparty_id=seller_id, plate_id=plate_id, amount=-price,
                transaction_type="SALE", metadata={"sale_id": sale["id"], "commission": split.fee_amount},
            )
            await self.repos.transactions.create(
                conn, user_id=seller_id, counterparty_id=buyer_id, plate_id=plate_id, amount=split.seller_amount,
                transaction_type="SALE", metadata={"sale_id": sale["id"], "commission": split.fee_amount},
            )
            await self.repos.transactions.ownership(conn, plate_id, seller_id, buyer_id, "FIXED_SALE", price)
            await self.repos.notifications.enqueue(conn, seller_id, "SALE_COMPLETED", {"plate_number": plate["plate_number"], "amount": split.seller_amount})
            await self.repos.notifications.enqueue(conn, buyer_id, "PLATE_PURCHASED", {"plate_number": plate["plate_number"]})
            logger.info("fixed_sale_completed", extra={"plate_id": plate_id, "buyer_id": buyer_id, "seller_id": seller_id, "amount": price})
            return {"plate_number": plate["plate_number"], "price": price, "seller_amount": split.seller_amount, "commission": split.fee_amount}

    async def cancel(self, seller_id: int, plate_id: int) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            plate = await self.repos.plates.lock(conn, plate_id)
            sale = await self.repos.sales.lock_active_by_plate(conn, plate_id)
            if not plate or not sale or sale["seller_id"] != seller_id:
                raise DomainError("Активная продажа вашего номера не найдена.")
            await self.repos.sales.cancel(conn, sale["id"])
            await self.repos.plates.set_owner_and_state(conn, plate_id, seller_id, PlateState.OWNED)
