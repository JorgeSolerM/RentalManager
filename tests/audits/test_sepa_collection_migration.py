import sqlite3
from contextlib import closing

from alembic import command
from alembic.config import Config
import pytest


@pytest.mark.alembic_audit
def test_sepa_collection_roundtrip_no_backfill(tmp_path, monkeypatch):
    path = tmp_path / 'collections_roundtrip.db'
    monkeypatch.setenv('DATABASE_URL', f'sqlite:///{path.as_posix()}')
    monkeypatch.setenv('ALEMBIC_REQUIRE_TEMPORARY_DATABASE', '1')
    config = Config('alembic.ini')
    command.upgrade(config, 'e7a9b1c3d560')
    tables = {'sepa_settings','sepa_batches','sepa_batch_groups','sepa_debits','sepa_debit_charge_allocations','sepa_export_artifacts'}
    for operation, revision in [(command.upgrade, 'f8b0d2e4a671'), (command.downgrade, 'e7a9b1c3d560'), (command.upgrade, 'f8b0d2e4a671')]:
        operation(config, revision)
        with closing(sqlite3.connect(path)) as connection:
            actual = {r[0] for r in connection.execute("select name from sqlite_master where type='table'")}
            assert tables.issubset(actual) if revision == 'f8b0d2e4a671' else not tables.intersection(actual)
            if revision == 'f8b0d2e4a671':
                assert all(connection.execute(f'select count(*) from {t}').fetchone()[0] == 0 for t in tables)
            assert connection.execute('pragma quick_check').fetchone() == ('ok',)
            assert connection.execute('pragma foreign_key_check').fetchall() == []
