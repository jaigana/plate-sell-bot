from __future__ import annotations

import logging

from datetime import datetime, timedelta, timezone

from app.domain import AuctionStatus, DomainError, NotFoundError, PlateState, split_sale_amount
from app.services.common import Service, setting_int

logger = logging.getLogger(__name__)


class AuctionService(Service):
    async def create(self, seller_id: int, plate_id: int, starting_price: int, duration_minutes: int) -> dict:
        if not 1 <= starting_price <= 99_999 or not 1 <= duration_minutes <= 1_440:
            raise DomainError("Проверьте стартовую цену и длительность аукциона (до 24 часов).")
        async with self.pool.acquire() as conn, conn.transaction():
            plate = await self.repos.plates.lock(conn, plate_id)
            if not plate:
                raise NotFoundError("Номер не найден.")
            if plate["owner_id"] != seller_id or plate["state"] != PlateState.OWNED:
                raise DomainError("На аукцион можно выставить только свой свободный номер.")
            ends_at = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
            auction = await self.repos.auctions.create(conn, plate_id, seller_id, starting_price, ends_at)
            await self.repos.plates.set_owner_and_state(conn, plate_id, seller_id, PlateState.AUCTION)
            return dict(auction)

    async def list_active(self) -> list[dict]:
        async with self.pool.acquire() as conn:
            return [dict(row) for row in await self.repos.auctions.active(conn)]

    async def get(self, auction_id: int) -> dict:
        async with self.pool.acquire() as conn:
            row = await self.repos.auctions.get(conn, auction_id)
            if not row:
                raise NotFoundError("Аукцион не найден.")
            return dict(row)

    async def bid_history(self, auction_id: int) -> list[dict]:
        async with self.pool.acquire() as conn:
            return [dict(row) for row in await self.repos.auctions.bid_history(conn, auction_id)]

    async def place_bid(self, bidder_id: int, auction_id: int, amount: int) -> dict:
        async with self.pool.acquire() as conn, conn.transaction():
            auction = await self.repos.auctions.lock(conn, auction_id)
            if not auction or auction["status"] != AuctionStatus.ACTIVE:
                raise DomainError("Этот аукцион уже завершён.")
            now = datetime.now(timezone.utc)
            if auction["ends_at"] <= now:
                raise DomainError("Время аукциона истекло.")
            if auction["seller_id"] == bidder_id:
                raise DomainError("Продавец не может делать ставки на свой аукцион.")
            previous_bidder = auction["highest_bidder_id"]
            if previous_bidder == bidder_id:
                raise DomainError("Вы уже лидируете в этом аукционе.")
            increment = await setting_int(conn, self.repos, "auction_min_increment")
            minimum = auction["current_price"] if previous_bidder is None else auction["current_price"] + increment
            if amount < minimum:
                raise DomainError(f"Минимальная ставка: ⭐{minimum}.")
            users = await self.repos.users.lock_many(conn, [bidder_id] + ([previous_bidder] if previous_bidder else []))
            bidder = users.get(bidder_id)
            if not bidder or bidder["is_blocked"]:
                raise DomainError("Ваш аккаунт заблокирован или не найден.")
            if bidder["balance_available"] < amount:
                raise DomainError("Недостаточно доступных ⭐ для ставки.")
            if previous_bidder:
                previous = users.get(previous_bidder)
                if not previous or previous["balance_frozen"] < auction["current_price"]:
                    raise DomainError("Целостность предыдущей ставки нарушена; обратитесь к администратору.")
                await self.repos.users.set_balances(
                    conn, previous_bidder, previous["balance_available"] + auction["current_price"],
                    previous["balance_frozen"] - auction["current_price"],
                )
                await self.repos.notifications.enqueue(conn, previous_bidder, "AUCTION_OUTBID", {"auction_id": auction_id, "amount": amount})
            await self.repos.users.set_balances(conn, bidder_id, bidder["balance_available"] - amount, bidder["balance_frozen"] + amount)
            anti_snipe = await setting_int(conn, self.repos, "auction_anti_snipe_minutes")
            extension = await setting_int(conn, self.repos, "auction_extension_minutes")
            ends_at = auction["ends_at"]
            if ends_at - now <= timedelta(minutes=anti_snipe):
                ends_at += timedelta(minutes=extension)
            await self.repos.auctions.add_bid(conn, auction_id, bidder_id, amount)
            await self.repos.auctions.update_highest(conn, auction_id, amount, bidder_id, ends_at)
            logger.info("auction_bid_placed", extra={"auction_id": auction_id, "bidder_id": bidder_id, "amount": amount})
            return {"auction_id": auction_id, "amount": amount, "ends_at": ends_at}

    async def finish_due(self) -> int:
        async with self.pool.acquire() as conn:
            due_ids = await self.repos.auctions.due_ids(conn)
        completed = 0
        for auction_id in due_ids:
            if await self.finish(auction_id):
                completed += 1
        return completed

    async def finish(self, auction_id: int, *, force: bool = False) -> bool:
        async with self.pool.acquire() as conn, conn.transaction():
            auction = await self.repos.auctions.lock(conn, auction_id)
            if not auction or auction["status"] != AuctionStatus.ACTIVE:
                return False
            if not force and auction["ends_at"] > datetime.now(timezone.utc):
                return False
            plate = await self.repos.plates.lock(conn, auction["plate_id"])
            if not plate:
                raise DomainError("Номер аукциона не найден.")
            winner_id = auction["highest_bidder_id"]
            if winner_id is None:
                await self.repos.auctions.finish(conn, auction_id)
                await self.repos.plates.set_owner_and_state(conn, plate["id"], auction["seller_id"], PlateState.OWNED)
                await self.repos.notifications.enqueue(conn, auction["seller_id"], "AUCTION_FINISHED", {"auction_id": auction_id, "winner": None})
                return True
            users = await self.repos.users.lock_many(conn, [auction["seller_id"], winner_id])
            seller, winner = users.get(auction["seller_id"]), users.get(winner_id)
            if not seller or not winner or winner["balance_frozen"] < auction["current_price"]:
                raise DomainError("Целостность аукционной сделки нарушена; требуется администратор.")
            commission = await setting_int(conn, self.repos, "commission_percent")
            split = split_sale_amount(auction["current_price"], commission)
            await self.repos.users.set_balances(
                conn, winner_id, winner["balance_available"], winner["balance_frozen"] - auction["current_price"]
            )
            await self.repos.users.set_balances(
                conn, seller["telegram_id"], seller["balance_available"] + split.seller_amount, seller["balance_frozen"]
            )
            await self.repos.auctions.finish(conn, auction_id)
            await self.repos.plates.set_owner_and_state(conn, plate["id"], winner_id, PlateState.OWNED)
            await self.repos.transactions.create(
                conn, user_id=winner_id, counterparty_id=auction["seller_id"], plate_id=plate["id"], amount=-auction["current_price"],
                transaction_type="AUCTION_SALE", metadata={"auction_id": auction_id, "commission": split.fee_amount},
            )
            await self.repos.transactions.create(
                conn, user_id=auction["seller_id"], counterparty_id=winner_id, plate_id=plate["id"], amount=split.seller_amount,
                transaction_type="AUCTION_SALE", metadata={"auction_id": auction_id, "commission": split.fee_amount},
            )
            await self.repos.transactions.ownership(conn, plate["id"], auction["seller_id"], winner_id, "AUCTION", auction["current_price"])
            await self.repos.notifications.enqueue(conn, winner_id, "AUCTION_WON", {"plate_number": plate["plate_number"], "amount": auction["current_price"]})
            await self.repos.notifications.enqueue(conn, auction["seller_id"], "AUCTION_FINISHED", {"plate_number": plate["plate_number"], "amount": split.seller_amount})
            logger.info("auction_finished", extra={"auction_id": auction_id, "winner_id": winner_id, "seller_id": auction["seller_id"], "amount": auction["current_price"]})
            return True

    async def cancel(self, seller_id: int, auction_id: int) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            auction = await self.repos.auctions.lock(conn, auction_id)
            if not auction or auction["status"] != AuctionStatus.ACTIVE or auction["seller_id"] != seller_id:
                raise DomainError("Активный аукцион не найден.")
            if auction["highest_bidder_id"] is not None:
                raise DomainError("Аукцион со ставками отменить нельзя.")
            plate = await self.repos.plates.lock(conn, auction["plate_id"])
            await self.repos.auctions.cancel(conn, auction_id)
            await self.repos.plates.set_owner_and_state(conn, plate["id"], seller_id, PlateState.OWNED)

    async def force_cancel(self, auction_id: int) -> None:
        """Administrative cancellation; any held highest bid is released atomically."""
        async with self.pool.acquire() as conn, conn.transaction():
            auction = await self.repos.auctions.lock(conn, auction_id)
            if not auction or auction["status"] != AuctionStatus.ACTIVE:
                raise DomainError("Активный аукцион не найден.")
            plate = await self.repos.plates.lock(conn, auction["plate_id"])
            if auction["highest_bidder_id"]:
                users = await self.repos.users.lock_many(conn, [auction["highest_bidder_id"]])
                bidder = users.get(auction["highest_bidder_id"])
                if not bidder or bidder["balance_frozen"] < auction["current_price"]:
                    raise DomainError("Нельзя безопасно разморозить текущую ставку.")
                await self.repos.users.set_balances(
                    conn, bidder["telegram_id"], bidder["balance_available"] + auction["current_price"],
                    bidder["balance_frozen"] - auction["current_price"],
                )
            await self.repos.auctions.cancel(conn, auction_id)
            await self.repos.plates.set_owner_and_state(conn, plate["id"], auction["seller_id"], PlateState.OWNED)
