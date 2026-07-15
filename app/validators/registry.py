from __future__ import annotations

from dataclasses import dataclass

from .base import PlateValidationError, PlateValidator
from .kz import PlateValidatorKZ
from .ru import PlateValidatorRU


@dataclass(frozen=True, slots=True)
class Country:
    code: str
    name: str
    active: bool
    validator: PlateValidator | None = None
    example: str = ""
    format_hint: str = ""


class CountryRegistry:
    def __init__(self) -> None:
        self._countries: dict[str, Country] = {
            "RU": Country(
                "RU", "Россия", True, PlateValidatorRU(), "А001АА77",
                "Пример: А001АА77 · только кириллица А В Е К М Н О Р С Т У Х; латиница A, B, C запрещена.",
            ),
            "KZ": Country(
                "KZ", "Казахстан", True, PlateValidatorKZ(), "777AAA01",
                "Физлицо: 777AAA01 · юрлицо: 001AA01 · только английские A–Z; кириллица А, В, С запрещена.",
            ),
            "UA": Country("UA", "Украина", False),
            "BY": Country("BY", "Беларусь", False),
            "KG": Country("KG", "Кыргызстан", False),
            "UZ": Country("UZ", "Узбекистан", False),
            "TJ": Country("TJ", "Таджикистан", False),
            "TM": Country("TM", "Туркменистан", False),
            "AM": Country("AM", "Армения", False),
            "AZ": Country("AZ", "Азербайджан", False),
            "MD": Country("MD", "Молдова", False),
        }

    def active(self) -> tuple[Country, ...]:
        return tuple(country for country in self._countries.values() if country.active)

    def get(self, country_code: str) -> Country:
        try:
            return self._countries[country_code.upper()]
        except KeyError as exc:
            raise PlateValidationError("Неизвестная страна.") from exc

    def validate(self, country_code: str, value: str, *, forbidden_series: set[str] | None = None) -> str:
        country = self.get(country_code)
        if not country.active or country.validator is None:
            raise PlateValidationError("Для этой страны валидатор пока не подключён.")
        return country.validator.validate(value, forbidden_series=forbidden_series)


country_registry = CountryRegistry()
