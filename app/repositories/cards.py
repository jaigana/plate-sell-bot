from __future__ import annotations

import asyncpg


class CardRepository:
    async def get(self, conn: asyncpg.Connection, card_id: str) -> asyncpg.Record | None:
        return await conn.fetchrow("SELECT * FROM bot_cards WHERE card_id=$1 AND enabled", card_id)

    async def list_all(self, conn: asyncpg.Connection) -> list[asyncpg.Record]:
        return list(await conn.fetch("SELECT * FROM bot_cards ORDER BY card_id"))

    async def upsert(
        self, conn: asyncpg.Connection, card_id: str, title: str, description: str, image_file_id: str | None, actor_id: int
    ) -> None:
        await conn.execute(
            """INSERT INTO bot_cards(card_id,title,description,image_file_id,updated_by)
            VALUES($1,$2,$3,$4,$5)
            ON CONFLICT(card_id) DO UPDATE SET title=EXCLUDED.title,description=EXCLUDED.description,
            image_file_id=EXCLUDED.image_file_id,updated_by=EXCLUDED.updated_by,updated_at=now()""",
            card_id, title, description, image_file_id, actor_id,
        )

