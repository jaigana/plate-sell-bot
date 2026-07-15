from __future__ import annotations

from typing import Sequence

import asyncpg


class PlateRepository:
    async def create_state_sale(
        self, conn: asyncpg.Connection, country_code: str, plate_number: str, reserved_by: int | None = None
    ) -> asyncpg.Record:
        return await conn.fetchrow(
            """
            INSERT INTO plates(country_code, plate_number, state, reserved_by, reserved_until)
            VALUES(
                $1, $2, 'STATE_SALE', $3::bigint,
                CASE WHEN $3::bigint IS NULL THEN NULL ELSE now() + interval '5 minutes' END
            )
            RETURNING *
            """, country_code, plate_number, reserved_by,
        )

    async def get(self, conn: asyncpg.Connection, plate_id: int) -> asyncpg.Record | None:
        return await conn.fetchrow("SELECT * FROM plates WHERE id=$1", plate_id)

    async def get_by_number(self, conn: asyncpg.Connection, plate_number: str) -> asyncpg.Record | None:
        return await conn.fetchrow("SELECT * FROM plates WHERE plate_number=$1", plate_number)

    async def lock(self, conn: asyncpg.Connection, plate_id: int) -> asyncpg.Record | None:
        return await conn.fetchrow("SELECT * FROM plates WHERE id=$1 FOR UPDATE", plate_id)

    async def lock_by_number(self, conn: asyncpg.Connection, plate_number: str) -> asyncpg.Record | None:
        return await conn.fetchrow("SELECT * FROM plates WHERE plate_number=$1 FOR UPDATE", plate_number)

    async def search(self, conn: asyncpg.Connection, query: str, country_code: str | None = None) -> list[asyncpg.Record]:
        if country_code:
            rows = await conn.fetch(
                """
                SELECT p.*, s.price AS sale_price FROM plates p
                LEFT JOIN sales s ON s.plate_id=p.id AND s.status='ACTIVE'
                WHERE p.country_code=$1 AND p.plate_number ILIKE '%' || $2 || '%'
                ORDER BY p.updated_at DESC LIMIT 15
                """, country_code, query,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT p.*, s.price AS sale_price FROM plates p
                LEFT JOIN sales s ON s.plate_id=p.id AND s.status='ACTIVE'
                WHERE p.plate_number ILIKE '%' || $1 || '%'
                ORDER BY p.updated_at DESC LIMIT 15
                """, query,
            )
        return list(rows)

    async def list_owned(self, conn: asyncpg.Connection, user_id: int) -> list[asyncpg.Record]:
        return list(await conn.fetch("SELECT * FROM plates WHERE owner_id=$1 ORDER BY updated_at DESC", user_id))

    async def list_market(self, conn: asyncpg.Connection, country_code: str | None = None) -> list[asyncpg.Record]:
        where = "p.state IN ('STATE_SALE','FIXED_SALE','AUCTION')"
        args: tuple[object, ...] = ()
        if country_code:
            where += " AND p.country_code=$1"
            args = (country_code,)
        return list(await conn.fetch(
            f"""SELECT p.*, s.price AS sale_price, a.id AS auction_id, a.current_price, a.ends_at
            FROM plates p LEFT JOIN sales s ON s.plate_id=p.id AND s.status='ACTIVE'
            LEFT JOIN auctions a ON a.plate_id=p.id AND a.status='ACTIVE'
            WHERE {where} ORDER BY p.updated_at DESC LIMIT 20""", *args
        ))

    async def set_owner_and_state(
        self, conn: asyncpg.Connection, plate_id: int, owner_id: int | None, state: str
    ) -> None:
        await conn.execute(
            """UPDATE plates SET owner_id=$2, state=$3, reserved_by=NULL, reserved_until=NULL, updated_at=now()
            WHERE id=$1""", plate_id, owner_id, state,
        )

    async def reserve(self, conn: asyncpg.Connection, plate_id: int, user_id: int) -> None:
        await conn.execute(
            "UPDATE plates SET reserved_by=$2, reserved_until=now()+interval '5 minutes', updated_at=now() WHERE id=$1",
            plate_id, user_id,
        )

    async def release_expired_reservations(self, conn: asyncpg.Connection) -> list[int]:
        rows = await conn.fetch(
            """UPDATE plates SET reserved_by=NULL, reserved_until=NULL, updated_at=now()
            WHERE reserved_until < now() RETURNING id"""
        )
        return [row["id"] for row in rows]

    async def return_owned_to_state(self, conn: asyncpg.Connection, user_id: int) -> list[asyncpg.Record]:
        return list(await conn.fetch(
            """UPDATE plates SET owner_id=NULL, state='STATE_SALE', reserved_by=NULL, reserved_until=NULL, updated_at=now()
            WHERE owner_id=$1 AND state='OWNED' RETURNING *""", user_id
        ))
