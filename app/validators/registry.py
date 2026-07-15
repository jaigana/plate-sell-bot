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


class CountryRegistry:
    def __init__(self) -> None:
        self._countries: dict[str, Country] = {
            "RU": Country("RU", "Россия", True, PlateValidatorRU()),
            "KZ": Country("KZ", "Казахстан", True, PlateValidatorKZ()),
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

    def validate(self, country_code: str, value: str, *, blacklisted_series: set[str] | None = None) -> str:
        country = self.get(country_code)
        if not country.active or country.validator is None:
            raise PlateValidationError("Для этой страны валидатор пока не подключён.")
        return country.validator.validate(value, blacklisted_series=blacklisted_series)


country_registry = CountryRegistry()
