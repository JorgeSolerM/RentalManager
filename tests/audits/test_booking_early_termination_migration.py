import sqlite3
from contextlib import closing
from alembic import command
from alembic.config import Config
import pytest


@pytest.mark.alembic_audit
def test_early_termination_migration_cycle(tmp_path,monkeypatch):
    path=tmp_path/'early_migration.db'
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+path.as_posix())
    monkeypatch.setenv('ALEMBIC_REQUIRE_TEMPORARY_DATABASE','1')
    cfg=Config('alembic.ini')
    command.upgrade(cfg,'fe0618cad237')
    for action,revision in ((command.upgrade,'b1283aedf459'),(command.downgrade,'fe0618cad237'),(command.upgrade,'b1283aedf459')):
        action(cfg,revision)
        with closing(sqlite3.connect(path)) as db:
            assert db.execute('PRAGMA quick_check').fetchone()==('ok',)
            assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert db.execute('SELECT version_num FROM alembic_version').fetchone()==(revision,)
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT COUNT(*) FROM booking_early_terminations').fetchone()==(0,)
        assert len(db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'early_termination_%'").fetchall())==3
        assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='management_fee_invoices'").fetchone()==(0,)
