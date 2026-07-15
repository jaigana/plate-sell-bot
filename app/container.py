from __future__ import annotations

import asyncpg

from app.config import Settings
from app.services import (
    AdminService, AuctionService, BackupService, BalanceService, CardService, EmissionService,
    NotificationService, PlateService, ReservationService, SaleService, UserService,
)
from app.services.common import Repositories


class AppContext:
    def __init__(self, settings: Settings, pool: asyncpg.Pool) -> None:
        self.settings = settings
        self.pool = pool
        self.repositories = Repositories()
        self.users = UserService(pool, self.repositories)
        self.plates = PlateService(pool, self.repositories)
        self.emission = EmissionService(pool, self.repositories)
        self.reservations = ReservationService(pool, self.repositories)
        self.balance = BalanceService(pool, self.repositories)
        self.sales = SaleService(pool, self.repositories)
        self.auctions = AuctionService(pool, self.repositories)
        self.notifications = NotificationService(pool, self.repositories)
        self.cards = CardService(pool, self.repositories)
        self.admin = AdminService(pool, self.repositories, settings.admin_ids)
        self.backups = BackupService(pool, self.repositories, settings.database_url, settings.owner_telegram_id)
