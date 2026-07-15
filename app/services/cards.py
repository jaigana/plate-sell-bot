from __future__ import annotations

from app.domain import DomainError
from app.services.common import Service


class CardService(Service):
    async def get(self, card_id: str) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await self.repos.cards.get(conn, card_id)
            return dict(row) if row else None

    async def list_all(self) -> list[dict]:
        async with self.pool.acquire() as conn:
            return [dict(row) for row in await self.repos.cards.list_all(conn)]

    async def update(self, actor_id: int, card_id: str, title: str, description: str, image_file_id: str | None) -> None:
        if not card_id.replace("_", "").isalnum() or len(card_id) > 50:
            raise DomainError("Недопустимый идентификатор карточки.")
        if not title.strip() or len(title) > 150 or len(description) > 4_000:
            raise DomainError("Проверьте заголовок и описание карточки.")
        async with self.pool.acquire() as conn, conn.transaction():
            await self.repos.cards.upsert(conn, card_id, title.strip(), description.strip(), image_file_id, actor_id)
            await self.repos.admin.audit(conn, actor_id, "card_update", "bot_card", card_id, {})
