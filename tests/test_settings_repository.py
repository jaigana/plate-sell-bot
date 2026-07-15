import asyncpg
import pytest

from app.repositories.settings import SettingsRepository


class _NeverQueryConnection:
    async def fetch(self, query: str, *args: object) -> list[object]:
        raise AssertionError("RU validation must not query the KZ rules table")


class _MissingRulesConnection:
    async def fetch(self, query: str, *args: object) -> list[object]:
        raise asyncpg.UndefinedTableError("official_forbidden_plate_series")


@pytest.mark.asyncio
async def test_non_kz_countries_do_not_depend_on_kz_rules_migration() -> None:
    assert await SettingsRepository().official_forbidden_series(_NeverQueryConnection(), "RU") == set()  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_kz_uses_fallback_rules_when_migration_is_not_available() -> None:
    assert "SEX" in await SettingsRepository().official_forbidden_series(_MissingRulesConnection(), "KZ")  # type: ignore[arg-type]
