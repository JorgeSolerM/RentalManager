import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


@pytest.mark.alembic_audit
def test_sepa_schema_upgrade_downgrade_reupgrade_without_backfill(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "sepa_round_trip.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("ALEMBIC_REQUIRE_TEMPORARY_DATABASE", "1")
    config = Config("alembic.ini")
    command.upgrade(config, "c5e7a9b1d348")

    command.upgrade(config, "d6f8a0b2c459")
    connection = sqlite3.connect(database_path)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"sepa_creditor_profiles", "sepa_mandates", "booking_sepa_mandates"} <= tables
    assert connection.execute("SELECT COUNT(*) FROM sepa_creditor_profiles").fetchone() == (0,)
    assert connection.execute("SELECT COUNT(*) FROM sepa_mandates").fetchone() == (0,)
    assert connection.execute("SELECT COUNT(*) FROM booking_sepa_mandates").fetchone() == (0,)
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()

    command.downgrade(config, "c5e7a9b1d348")
    connection = sqlite3.connect(database_path)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "sepa_creditor_profiles" not in tables
    assert "sepa_mandates" not in tables
    assert "booking_sepa_mandates" not in tables
    connection.close()

    command.upgrade(config, "d6f8a0b2c459")
    connection = sqlite3.connect(database_path)
    assert connection.execute("PRAGMA quick_check").fetchone() == ("ok",)
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("d6f8a0b2c459",)
    connection.close()
