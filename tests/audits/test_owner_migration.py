import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


@pytest.mark.alembic_audit
def test_owner_schema_upgrade_downgrade_reupgrade(tmp_path, monkeypatch):
    database_path = Path(tmp_path) / "owners.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("ALEMBIC_REQUIRE_TEMPORARY_DATABASE", "1")
    config = Config("alembic.ini")
    command.upgrade(config, "b4d6f8a0c237")
    connection = sqlite3.connect(database_path)
    connection.execute("INSERT INTO properties (id,name,address,city,owner,active,is_published) VALUES (1,'P','A','C','legacy',1,0)")
    connection.commit(); connection.close()

    command.upgrade(config, "c5e7a9b1d348")
    connection = sqlite3.connect(database_path)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"owners", "owner_bank_accounts", "property_ownerships"} <= tables
    assert connection.execute("SELECT owner FROM properties WHERE id=1").fetchone()[0] == "legacy"
    assert connection.execute("SELECT COUNT(*) FROM owners").fetchone()[0] == 0
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()

    command.downgrade(config, "b4d6f8a0c237")
    command.upgrade(config, "c5e7a9b1d348")
    connection = sqlite3.connect(database_path)
    assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    connection.close()
