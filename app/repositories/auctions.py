from __future__ import annotations

from datetime import datetime

import asyncpg


class AuctionRepository:
    async def create(
        self, conn: asyncpg.Connection, plate_id: int, seller_id: int, starting_price: int, ends_at: datetime
    ) -> asyncpg.Record:
        return await conn.fetchrow(
            """INSERT INTO auctions(plate_id,seller_id,starting_price,current_price,ends_at)
            VALUES($1,$2,$3,$3,$4) RETURNING *""", plate_id, seller_id, starting_price, ends_at
        )

    async def get(self, conn: asyncpg.Connection, auction_id: int) -> asyncpg.Record | None:
        return await conn.fetchrow("SELECT * FROM auctions WHERE id=$1", auction_id)

    async def lock(self, conn: asyncpg.Connection, auction_id: int) -> asyncpg.Record | None:
        return await conn.fetchrow("SELECT * FROM auctions WHERE id=$1 FOR UPDATE", auction_id)

    async def lock_active_by_plate(self, conn: asyncpg.Connection, plate_id: int) -> asyncpg.Record | None:
        return await conn.fetchrow("SELECT * FROM auctions WHERE plate_id=$1 AND status='ACTIVE' FOR UPDATE", plate_id)

    async def active(self, conn: asyncpg.Connection, limit: int = 20) -> list[asyncpg.Record]:
        return list(await conn.fetch(
            """SELECT a.*, p.plate_number, p.country_code FROM auctions a JOIN plates p ON p.id=a.plate_id
            WHERE a.status='ACTIVE' ORDER BY a.ends_at ASC LIMIT $1""", limit
        ))

    async def due_ids(self, conn: asyncpg.Connection) -> list[int]:
        return [row["id"] for row in await conn.fetch("SELECT id FROM auctions WHERE status='ACTIVE' AND ends_at <= now()")]

    async def add_bid(self, conn: asyncpg.Connection, auction_id: int, bidder_id: int, amount: int) -> None:
        await conn.execute("INSERT INTO bids(auction_id,bidder_id,amount) VALUES($1,$2,$3)", auction_id, bidder_id, amount)

    async def bid_history(self, conn: asyncpg.Connection, auction_id: int) -> list[asyncpg.Record]:
        return list(await conn.fetch(
            "SELECT * FROM bids WHERE auction_id=$1 ORDER BY amount DESC, created_at ASC", auction_id
        ))

    async def update_highest(
        self, conn: asyncpg.Connection, auction_id: int, amount: int, bidder_id: int, ends_at: datetime
    ) -> None:
        await conn.execute(
            """UPDATE auctions SET current_price=$2, highest_bidder_id=$3, ends_at=$4, updated_at=now()
            WHERE id=$1""", auction_id, amount, bidder_id, ends_at
        )

    async def finish(self, conn: asyncpg.Connection, auction_id: int) -> None:
        await conn.execute("UPDATE auctions SET status='FINISHED', updated_at=now() WHERE id=$1", auction_id)

    async def cancel(self, conn: asyncpg.Connection, auction_id: int) -> None:
        await conn.execute("UPDATE auctions SET status='CANCELLED', updated_at=now() WHERE id=$1", auction_id)
