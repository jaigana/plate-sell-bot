import pytest

from app.validators.base import PlateValidationError
from app.validators.registry import country_registry


def test_ru_validates_cyrillic_plate() -> None:
    assert country_registry.validate("RU", " а 001 аа 77 ") == "А001АА77"


@pytest.mark.parametrize("value", ["A777AA77", "Α777АА77", "А777АA77", "А000АА00"])
def test_ru_rejects_latin_greek_mixed_or_unknown_region(value: str) -> None:
    with pytest.raises(PlateValidationError):
        country_registry.validate("RU", value)


@pytest.mark.parametrize("value", ["777AAA01", "001AA20"])
def test_kz_validates_both_formats(value: str) -> None:
    assert country_registry.validate("KZ", value) == value


@pytest.mark.parametrize("value", ["777SEX01", "001AA21", "777ААА01", "777AAA00"])
def test_kz_rejects_blacklist_homoglyph_and_bad_region(value: str) -> None:
    with pytest.raises(PlateValidationError):
        country_registry.validate("KZ", value)
