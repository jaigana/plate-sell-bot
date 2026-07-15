from __future__ import annotations

from datetime import datetime, timezone

from app.domain import DomainError, PlateState
from app.services.common import Service


class ReservationService(Service):
    async def reserve_existing_state_plate(self, plate_id: int, user_id: int) -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            plate = await self.repos.plates.lock(conn, plate_id)
            if not plate:
                raise DomainError("Номер не найден.")
            if plate["state"] != PlateState.STATE_SALE:
                raise DomainError("Этот номер сейчас нельзя зарезервировать.")
            if plate["reserved_until"] and plate["reserved_until"] > datetime.now(timezone.utc) and plate["reserved_by"] != user_id:
                raise DomainError("Номер уже временно зарезервирован другим игроком.")
            await self.repos.plates.reserve(conn, plate_id, user_id)

    async def release_expired(self) -> int:
        async with self.pool.acquire() as conn, conn.transaction():
            return len(await self.repos.plates.release_expired_reservations(conn))
