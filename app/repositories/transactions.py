from __future__ import annotations

from typing import Any

import asyncpg


class TransactionRepository:
    async def create(
        self, conn: asyncpg.Connection, *, user_id: int | None, counterparty_id: int | None, plate_id: int | None,
        amount: int, transaction_type: str, status: str = "COMPLETED", external_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> asyncpg.Record:
        return await conn.fetchrow(
            """INSERT INTO transactions(user_id,counterparty_id,plate_id,amount,transaction_type,status,external_ref,metadata)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb) RETURNING *""",
            user_id, counterparty_id, plate_id, amount, transaction_type, status, external_ref, metadata or {},
        )

    async def get_by_external_ref(self, conn: asyncpg.Connection, external_ref: str) -> asyncpg.Record | None:
        return await conn.fetchrow("SELECT * FROM transactions WHERE external_ref=$1", external_ref)

    async def lock_by_external_ref(self, conn: asyncpg.Connection, external_ref: str) -> asyncpg.Record | None:
        return await conn.fetchrow("SELECT * FROM transactions WHERE external_ref=$1 FOR UPDATE", external_ref)

    async def lock_pending_mint(self, conn: asyncpg.Connection, user_id: int, plate_id: int) -> asyncpg.Record | None:
        return await conn.fetchrow(
            """SELECT * FROM transactions WHERE user_id=$1 AND plate_id=$2
            AND transaction_type='MINT_INVOICE' AND status='PENDING' ORDER BY id DESC LIMIT 1 FOR UPDATE""",
            user_id, plate_id,
        )

    async def update_status(self, conn: asyncpg.Connection, transaction_id: int, status: str) -> None:
        await conn.execute("UPDATE transactions SET status=$2 WHERE id=$1", transaction_id, status)

    async def ownership(
        self, conn: asyncpg.Connection, plate_id: int, previous_owner: int | None, new_owner: int | None, event_type: str, amount: int | None
    ) -> None:
        await conn.execute(
            """INSERT INTO ownership_history(plate_id,previous_owner_id,new_owner_id,event_type,amount)
            VALUES($1,$2,$3,$4,$5)""", plate_id, previous_owner, new_owner, event_type, amount
        )
