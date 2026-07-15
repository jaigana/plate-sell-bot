from __future__ import annotations

import re

from .base import PlateValidationError, PlateValidator, normalize_plate

DEFAULT_KZ_BLACKLIST = frozenset({"SEX", "ASS", "XXX", "BLY", "XER", "GEI"})
_PERSON = re.compile(r"^(\d{3})([A-Z]{3})(\d{2})$")
_LEGAL = re.compile(r"^(\d{3})([A-Z]{2})(\d{2})$")


class PlateValidatorKZ(PlateValidator):
    country_code = "KZ"

    def validate(self, value: str, *, blacklisted_series: set[str] | None = None) -> str:
        plate = normalize_plate(value)
        match = _PERSON.fullmatch(plate) or _LEGAL.fullmatch(plate)
        if not match:
            raise PlateValidationError(
                "Формат KZ: 777AAA01 (физлицо) или 001AA01 (юрлицо), только ASCII-латиница."
            )
        region = match.group(3)
        if not 1 <= int(region) <= 20:
            raise PlateValidationError("Регион Казахстана должен быть в диапазоне 01–20.")
        series = match.group(2)
        forbidden = DEFAULT_KZ_BLACKLIST | {item.upper() for item in (blacklisted_series or set())}
        if series in forbidden:
            raise PlateValidationError("Эта серия запрещена правилами площадки.")
        return plate

