from __future__ import annotations

import asyncpg

from app.repositories import (
    AdminRepository, AuctionRepository, BackupRepository, CardRepository, NotificationRepository, PlateRepository,
    SaleRepository, SettingsRepository, TransactionRepository, UserRepository,
)


class Repositories:
    def __init__(self) -> None:
        self.users = UserRepository()
        self.plates = PlateRepository()
        self.sales = SaleRepository()
        self.auctions = AuctionRepository()
        self.transactions = TransactionRepository()
        self.settings = SettingsRepository()
        self.notifications = NotificationRepository()
        self.cards = CardRepository()
        self.admin = AdminRepository()
        self.backups = BackupRepository()


class Service:
    def __init__(self, pool: asyncpg.Pool, repositories: Repositories) -> None:
        self.pool = pool
        self.repos = repositories


async def setting_int(conn: asyncpg.Connection, repositories: Repositories, key: str) -> int:
    value = await repositories.settings.get(conn, key)
    if isinstance(value, bool):
        raise ValueError(f"Setting {key} is not numeric")
    return int(value)
