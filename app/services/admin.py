from __future__ import annotations

from app.domain import AccessDenied, DomainError, NotFoundError, PlateState
from app.services.common import Service, setting_int

_NUMERIC_SETTINGS = {
    "mint_price", "commission_percent", "auction_min_increment", "auction_anti_snipe_minutes",
    "auction_extension_minutes", "inactive_days", "inactive_warning_days",
}


class AdminService(Service):
    def __init__(self, pool, repositories, configured_admin_ids: frozenset[int]) -> None:
        super().__init__(pool, repositories)
        self.configured_admin_ids = configured_admin_ids

    async def is_admin(self, user_id: int) -> bool:
        if user_id in self.configured_admin_ids:
            return True
        async with self.pool.acquire() as conn:
            return await self.repos.admin.is_admin(conn, user_id)

    async def require_admin(self, user_id: int) -> None:
        if not await self.is_admin(user_id):
            raise AccessDenied("Раздел доступен только администраторам.")

    async def stats(self, actor_id: int) -> dict[str, int]:
        await self.require_admin(actor_id)
        async with self.pool.acquire() as conn:
            return await self.repos.admin.stats(conn)

    async def grant_admin(self, actor_id: int, user_id: int) -> None:
        if actor_id not in self.configured_admin_ids:
            raise AccessDenied("Добавлять администраторов может только владелец бота.")
        async with self.pool.acquire() as conn, conn.transaction():
            user = await self.repos.users.get(conn, user_id)
            if not user:
                raise NotFoundError("Сначала пользователь должен открыть бота.")
            await self.repos.admin.grant(conn, user_id, actor_id)
            await self.repos.admin.audit(conn, actor_id, "grant_admin", "user", str(user_id), {})

    async def set_setting(self, actor_id: int, key: str, value: int) -> None:
        await self.require_admin(actor_id)
        if key not in _NUMERIC_SETTINGS or value < 0:
            raise DomainError("Недопустимая настройка или значение.")
        if key == "commission_percent" and value > 100:
            raise DomainError("Комиссия должна быть от 0 до 100 процентов.")
        if key == "mint_price" and not 1 <= value <= 99_999:
            raise DomainError("Цена эмиссии должна быть от 1 до 99 999.")
        if key == "auction_min_increment" and value < 1:
            raise DomainError("Минимальный шаг ставки должен быть не меньше 1.")
        if key in {"inactive_days", "inactive_warning_days"} and value < 1:
            raise DomainError("Срок неактивности должен быть не меньше одного дня.")
        async with self.pool.acquire() as conn, conn.transaction():
            if key == "inactive_warning_days" and value >= await setting_int(conn, self.repos, "inactive_days"):
                raise DomainError("Предупреждение должно быть раньше срока неактивности.")
            if key == "inactive_days" and value <= await setting_int(conn, self.repos, "inactive_warning_days"):
                raise DomainError("Срок неактивности должен быть больше срока предупреждения.")
            await self.repos.settings.set(conn, key, value, actor_id)
            await self.repos.admin.audit(conn, actor_id, "setting_update", "platform_setting", key, {"value": value})

    async def settings(self, actor_id: int) -> dict:
        await self.require_admin(actor_id)
        async with self.pool.acquire() as conn:
            return await self.repos.settings.all(conn)

    async def blacklist(self, actor_id: int) -> set[str]:
        await self.require_admin(actor_id)
        async with self.pool.acquire() as conn:
            return await self.repos.settings.kz_blacklist(conn)

    async def set_blacklist(self, actor_id: int, series: str, *, add: bool) -> None:
        await self.require_admin(actor_id)
        series = series.strip().upper()
        if not series.isascii() or not series.isalpha() or not 2 <= len(series) <= 3:
            raise DomainError("Серия должна состоять из 2–3 ASCII-латинских букв.")
        async with self.pool.acquire() as conn, conn.transaction():
            if add:
                await self.repos.settings.add_blacklist(conn, "KZ", series, actor_id)
            else:
                await self.repos.settings.remove_blacklist(conn, "KZ", series)
            await self.repos.admin.audit(conn, actor_id, "blacklist_update", "series", series, {"add": add})

    async def block(self, actor_id: int, user_id: int, reason: str) -> None:
        await self.require_admin(actor_id)
        if not reason.strip():
            raise DomainError("Укажите причину блокировки.")
        async with self.pool.acquire() as conn, conn.transaction():
            if not await self.repos.users.get(conn, user_id):
                raise NotFoundError("Пользователь не найден.")
            await self.repos.admin.block(conn, user_id, actor_id, reason.strip())
            await self.repos.admin.audit(conn, actor_id, "block_user", "user", str(user_id), {"reason": reason.strip()})

    async def unblock(self, actor_id: int, user_id: int) -> None:
        await self.require_admin(actor_id)
        async with self.pool.acquire() as conn, conn.transaction():
            if not await self.repos.users.get(conn, user_id):
                raise NotFoundError("Пользователь не найден.")
            await self.repos.admin.unblock(conn, user_id)
            await self.repos.admin.audit(conn, actor_id, "unblock_user", "user", str(user_id), {})

    async def force_transfer(self, actor_id: int, plate_id: int, new_owner_id: int | None) -> None:
        await self.require_admin(actor_id)
        async with self.pool.acquire() as conn, conn.transaction():
            plate = await self.repos.plates.lock(conn, plate_id)
            if not plate:
                raise NotFoundError("Номер не найден.")
            if new_owner_id is not None and not await self.repos.users.get(conn, new_owner_id):
                raise NotFoundError("Новый владелец не найден.")
            sale = await self.repos.sales.lock_active_by_plate(conn, plate_id)
            if sale:
                await self.repos.sales.cancel(conn, sale["id"])
            auction = await self.repos.auctions.lock_active_by_plate(conn, plate_id)
            if auction:
                if auction["highest_bidder_id"]:
                    users = await self.repos.users.lock_many(conn, [auction["highest_bidder_id"]])
                    bidder = users.get(auction["highest_bidder_id"])
                    if not bidder or bidder["balance_frozen"] < auction["current_price"]:
                        raise DomainError("Нельзя безопасно разморозить текущую ставку.")
                    await self.repos.users.set_balances(
                        conn, bidder["telegram_id"], bidder["balance_available"] + auction["current_price"],
                        bidder["balance_frozen"] - auction["current_price"],
                    )
                await self.repos.auctions.cancel(conn, auction["id"])
            await self.repos.plates.set_owner_and_state(
                conn, plate_id, new_owner_id, PlateState.OWNED if new_owner_id else PlateState.STATE_SALE
            )
            await self.repos.transactions.ownership(conn, plate_id, plate["owner_id"], new_owner_id, "ADMIN_TRANSFER", None)
            await self.repos.admin.audit(conn, actor_id, "force_transfer", "plate", str(plate_id), {"new_owner_id": new_owner_id})

    async def process_inactive_accounts(self) -> dict[str, int]:
        async with self.pool.acquire() as conn:
            days = await setting_int(conn, self.repos, "inactive_days")
            warning_days = await setting_int(conn, self.repos, "inactive_warning_days")
            inactive, warnings = await self.repos.users.list_inactive(conn, days, warning_days)
        returned = 0
        for user in inactive:
            async with self.pool.acquire() as conn, conn.transaction():
                # The update is intentionally conditional on current ownership, so an active transfer cannot be overwritten.
                plates = await self.repos.plates.return_owned_to_state(conn, user["telegram_id"])
                for plate in plates:
                    await self.repos.transactions.ownership(conn, plate["id"], user["telegram_id"], None, "INACTIVITY_RETURN", None)
                returned += len(plates)
        async with self.pool.acquire() as conn, conn.transaction():
            for user in warnings:
                await self.repos.notifications.enqueue(conn, user["telegram_id"], "ACCOUNT_INACTIVE_WARNING", {})
        return {"inactive_accounts": len(inactive), "returned_plates": returned, "warnings": len(warnings)}
