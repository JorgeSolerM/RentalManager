import sqlite3
from alembic import command
from alembic.config import Config
import pytest


@pytest.mark.alembic_audit
def test_reference_counter_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / 'reference_roundtrip.db'
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{path.as_posix()}')
    monkeypatch.setenv('ALEMBIC_REQUIRE_TEMPORARY_DATABASE', '1')
    config = Config('alembic.ini')
    command.upgrade(config, 'd6f8a0b2c459')
    for operation, revision in [(command.upgrade, 'e7a9b1c3d560'), (command.downgrade, 'd6f8a0b2c459'), (command.upgrade, 'e7a9b1c3d560')]:
        operation(config, revision)
        with sqlite3.connect(path) as connection:
            columns = {row[1] for row in connection.execute('pragma table_info(sepa_creditor_profiles)')}
            assert ('mandate_reference_counter' in columns) == (revision == 'e7a9b1c3d560')
            assert connection.execute('pragma quick_check').fetchone() == ('ok',)
            assert connection.execute('pragma foreign_key_check').fetchall() == []
