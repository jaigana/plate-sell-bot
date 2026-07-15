from pathlib import Path

import pytest

from app.db.migrator import apply_migrations


class _Transaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class _Connection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> None:
        self.executed.append((query, args))

    async def fetch(self, query: str) -> list[dict[str, str]]:
        return []

    def transaction(self) -> _Transaction:
        return _Transaction()


class _Acquire:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _Connection:
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class _Pool:
    def __init__(self) -> None:
        self.connection = _Connection()

    def acquire(self) -> _Acquire:
        return _Acquire(self.connection)


@pytest.mark.asyncio
async def test_migration_logging_does_not_overwrite_logrecord_filename(tmp_path: Path) -> None:
    (tmp_path / "0001_example.sql").write_text("SELECT 1;", encoding="utf-8")
    pool = _Pool()

    await apply_migrations(pool, tmp_path)  # type: ignore[arg-type]

    assert any(args == ("0001_example.sql",) for _, args in pool.connection.executed)
