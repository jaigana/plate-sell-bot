from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain import DomainError


class PlateValidationError(DomainError):
    pass


def normalize_plate(value: str) -> str:
    """Normalize harmless formatting only; never transliterate or repair homoglyphs."""
    if not isinstance(value, str):
        raise PlateValidationError("Номер должен быть текстом.")
    normalized = value.strip().replace(" ", "").replace("-", "").upper()
    if not normalized:
        raise PlateValidationError("Введите номер.")
    if len(normalized) > 15:
        raise PlateValidationError("Номер слишком длинный.")
    return normalized


class PlateValidator(ABC):
    country_code: str

    @abstractmethod
    def validate(self, value: str, *, forbidden_series: set[str] | None = None) -> str:
        raise NotImplementedError
