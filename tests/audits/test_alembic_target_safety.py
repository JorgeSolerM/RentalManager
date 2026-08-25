from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from backend.database.alembic_target import (
    REQUIRE_TEMPORARY_ENV,
    resolve_alembic_database_url,
    validate_alembic_target,
)
from backend.database.session import DATABASE_PATH, DATABASE_URL


def test_explicit_database_url_override_resolves_temporary_target(tmp_path, monkeypatch):
    temporary = tmp_path / "migration-copy.db"
    expected_url = f"sqlite:///{temporary.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", expected_url)
    monkeypatch.setenv(REQUIRE_TEMPORARY_ENV, "1")

    resolved_url = resolve_alembic_database_url()

    assert resolved_url == expected_url
    assert validate_alembic_target(resolved_url) == temporary.resolve()


def test_temporary_guard_rejects_real_database_before_alembic_connects(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv(REQUIRE_TEMPORARY_ENV, "1")

    with pytest.raises(RuntimeError, match="refused data/RentalManager.db"):
        validate_alembic_target(resolve_alembic_database_url())


def test_alembic_command_fails_fast_when_temporary_context_targets_real_database(
    monkeypatch,
):
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    monkeypatch.setenv(REQUIRE_TEMPORARY_ENV, "1")

    with pytest.raises(RuntimeError, match="refused data/RentalManager.db"):
        command.current(Config("alembic.ini"))


def test_normal_fallback_remains_the_rentalmanager_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv(REQUIRE_TEMPORARY_ENV, raising=False)

    assert resolve_alembic_database_url() == DATABASE_URL
    assert validate_alembic_target(DATABASE_URL) == Path(DATABASE_PATH).resolve()
