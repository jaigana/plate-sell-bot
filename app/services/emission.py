from __future__ import annotations

import logging
from uuid import uuid4

import asyncpg

from app.domain import DomainError, PlateState
from app.services.common import Service, setting_int
from app.validators.registry import country_registry

logger = logging.getLogger(__name__)


class EmissionService(Service):
    """Lazy minting through Telegram Stars invoices with a five-minute reservation."""

    async def prepare_invoice(self, user_id: int, country_code: str, raw_plate_number: str) -> dict:
        country_code = country_code.upper()
        async with self.pool.acquire() as conn, conn.transaction():
            blacklist = await self.repos.settings.kz_blacklist(conn) if country_code == "KZ" else set()
            plate_number = country_registry.validate(country_code, raw_plate_number, blacklisted_series=blacklist)
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", plate_number)
            users = await self.repos.users.lock_many(conn, [user_id])
            user = users.get(user_id)
            if not user or user["is_blocked"]:
                raise DomainError("Аккаунт заблокирован или не найден.")
            plate = await self.repos.plates.lock_by_number(conn, plate_number)
            if plate:
                if plate["state"] != PlateState.STATE_SALE or plate["owner_id"] is not None:
                    raise DomainError("Этот номер уже принадлежит игроку или выставлен на рынке.")
                reservation_active = plate["reserved_until"] and await conn.fetchval("SELECT $1 > now()", plate["reserved_until"])
                if reservation_active and plate["reserved_by"] != user_id:
                    raise DomainError("Этот номер уже зарезервирован другим игроком на время оплаты.")
                await self.repos.plates.reserve(conn, plate["id"], user_id)
            else:
                try:
                    plate = await self.repos.plates.create_state_sale(conn, country_code, plate_number, user_id)
                except asyncpg.UniqueViolationError as exc:
                    raise DomainError("Номер только что запросил другой игрок. Повторите поиск.") from exc
            transaction = await self.repos.transactions.lock_pending_mint(conn, user_id, plate["id"])
            if transaction is None:
                price = await setting_int(conn, self.repos, "mint_price")
                invoice_ref = f"mint-{uuid4().hex}"
                transaction = await self.repos.transactions.create(
                    conn, user_id=user_id, counterparty_id=None, plate_id=plate["id"], amount=price,
                    transaction_type="MINT_INVOICE", status="PENDING", external_ref=invoice_ref,
                    metadata={"country_code": country_code, "plate_number": plate_number},
                )
            return {"invoice_ref": transaction["external_ref"], "price": transaction["amount"], "plate_number": plate_number, "plate_id": plate["id"], "transaction_id": transaction["id"]}

    async def complete_invoice(self, user_id: int, invoice_ref: str, telegram_charge_id: str, paid_amount: int) -> dict:
        async with self.pool.acquire() as conn, conn.transaction():
            # The invoice reference is already unique and acts as our idempotency key.
            transaction = await self.repos.transactions.lock_by_external_ref(conn, invoice_ref)
            if not transaction:
                raise DomainError("Неизвестный счёт на эмиссию.")
            if transaction["user_id"] != user_id:
                raise DomainError("Этот счёт принадлежит другому пользователю.")
            if paid_amount != transaction["amount"]:
                raise DomainError("Сумма платежа не совпадает со счётом.")
            if transaction["status"] == "COMPLETED":
                plate = await self.repos.plates.get(conn, transaction["plate_id"])
                return dict(plate)
            duplicate_charge = await self.repos.transactions.get_by_external_ref(conn, telegram_charge_id)
            if duplicate_charge:
                raise DomainError("Этот платёж уже был обработан.")
            plate = await self.repos.plates.lock(conn, transaction["plate_id"])
            users = await self.repos.users.lock_many(conn, [user_id])
            if not plate or user_id not in users:
                raise DomainError("Не удалось завершить эмиссию.")
            if plate["reserved_by"] != user_id or not plate["reserved_until"] or not await conn.fetchval("SELECT $1 > now()", plate["reserved_until"]):
                raise DomainError("Срок резерва истёк. Обратитесь к администратору с идентификатором платежа.")
            await self.repos.plates.set_owner_and_state(conn, plate["id"], user_id, PlateState.OWNED)
            await self.repos.transactions.update_status(conn, transaction["id"], "COMPLETED")
            await self.repos.transactions.create(
                conn, user_id=user_id, counterparty_id=None, plate_id=plate["id"], amount=-transaction["amount"],
                transaction_type="MINT_INVOICE", external_ref=telegram_charge_id,
                metadata={"invoice_ref": invoice_ref, "kind": "telegram_charge"},
            )
            await self.repos.transactions.ownership(conn, plate["id"], None, user_id, "MINT", transaction["amount"])
            await self.repos.notifications.enqueue(conn, user_id, "PLATE_PURCHASED", {"plate_number": plate["plate_number"]})
            logger.info("plate_minted", extra={"plate_id": plate["id"], "user_id": user_id, "amount": transaction["amount"]})
            result = await self.repos.plates.get(conn, plate["id"])
            return dict(result)
