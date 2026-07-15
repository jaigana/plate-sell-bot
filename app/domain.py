from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PlateState(StrEnum):
    STATE_SALE = "STATE_SALE"
    OWNED = "OWNED"
    FIXED_SALE = "FIXED_SALE"
    AUCTION = "AUCTION"


class SaleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class AuctionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    FINISHED = "FINISHED"
    CANCELLED = "CANCELLED"


class TransactionType(StrEnum):
    MINT_INVOICE = "MINT_INVOICE"
    TOPUP = "TOPUP"
    SALE = "SALE"
    AUCTION_SALE = "AUCTION_SALE"
    ADMIN_ADJUSTMENT = "ADMIN_ADJUSTMENT"


class DomainError(Exception):
    """A safe, user-facing business-rule failure."""


class NotFoundError(DomainError):
    pass


class AccessDenied(DomainError):
    pass


@dataclass(frozen=True, slots=True)
class MoneySplit:
    seller_amount: int
    fee_amount: int


def split_sale_amount(amount: int, commission_percent: int) -> MoneySplit:
    if amount < 1:
        raise DomainError("Сумма должна быть положительным целым числом.")
    if not 0 <= commission_percent <= 100:
        raise DomainError("Комиссия платформы настроена некорректно.")
    fee = amount * commission_percent // 100
    return MoneySplit(seller_amount=amount - fee, fee_amount=fee)

