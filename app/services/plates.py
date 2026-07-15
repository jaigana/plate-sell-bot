from __future__ import annotations

from app.domain import NotFoundError
from app.services.common import Service
from app.validators.registry import country_registry


class PlateService(Service):
    async def normalize_and_validate(self, country_code: str, plate_number: str) -> str:
        async with self.pool.acquire() as conn:
            blacklist = await self.repos.settings.kz_blacklist(conn) if country_code.upper() == "KZ" else set()
            return country_registry.validate(country_code, plate_number, blacklisted_series=blacklist)

    async def search(self, raw_query: str, country_code: str | None = None) -> list[dict]:
        query = raw_query.strip().replace(" ", "").replace("-", "").upper()
        if not query or len(query) > 15:
            return []
        async with self.pool.acquire() as conn:
            return [dict(row) for row in await self.repos.plates.search(conn, query, country_code)]

    async def get(self, plate_id: int) -> dict:
        async with self.pool.acquire() as conn:
            row = await self.repos.plates.get(conn, plate_id)
            if not row:
                raise NotFoundError("Игровой номер не найден.")
            return dict(row)

    async def market(self, country_code: str | None = None) -> list[dict]:
        async with self.pool.acquire() as conn:
            return [dict(row) for row in await self.repos.plates.list_market(conn, country_code)]

    async def my_plates(self, user_id: int) -> list[dict]:
        async with self.pool.acquire() as conn:
            return [dict(row) for row in await self.repos.plates.list_owned(conn, user_id)]

