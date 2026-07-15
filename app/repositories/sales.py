from __future__ import annotations

import asyncpg


class SaleRepository:
    async def create(self, conn: asyncpg.Connection, plate_id: int, seller_id: int, price: int) -> asyncpg.Record:
        return await conn.fetchrow(
            "INSERT INTO sales(plate_id,seller_id,price) VALUES($1,$2,$3) RETURNING *", plate_id, seller_id, price
        )

    async def lock_active_by_plate(self, conn: asyncpg.Connection, plate_id: int) -> asyncpg.Record | None:
        return await conn.fetchrow("SELECT * FROM sales WHERE plate_id=$1 AND status='ACTIVE' FOR UPDATE", plate_id)

    async def lock(self, conn: asyncpg.Connection, sale_id: int) -> asyncpg.Record | None:
        return await conn.fetchrow("SELECT * FROM sales WHERE id=$1 FOR UPDATE", sale_id)

    async def complete(self, conn: asyncpg.Connection, sale_id: int, buyer_id: int) -> None:
        await conn.execute(
            "UPDATE sales SET status='COMPLETED', buyer_id=$2, completed_at=now(), updated_at=now() WHERE id=$1", sale_id, buyer_id
        )

    async def cancel(self, conn: asyncpg.Connection, sale_id: int) -> None:
        await conn.execute("UPDATE sales SET status='CANCELLED', updated_at=now() WHERE id=$1", sale_id)

