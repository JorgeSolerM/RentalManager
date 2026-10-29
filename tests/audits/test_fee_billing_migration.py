import sqlite3
from contextlib import closing
from alembic import command
from alembic.config import Config
import pytest


@pytest.mark.alembic_audit
def test_fee_billing_upgrade_downgrade_reupgrade(tmp_path,monkeypatch):
    path=tmp_path/'billing.db'
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+path.as_posix())
    monkeypatch.setenv('ALEMBIC_REQUIRE_TEMPORARY_DATABASE','1')
    cfg=Config('alembic.ini');command.upgrade(cfg,'b1283aedf459')
    with closing(sqlite3.connect(path)) as db:
        before=db.execute('SELECT id,code,name FROM expense_categories ORDER BY id').fetchall()
    for fn,revision in ((command.upgrade,'a01729dbe348'),(command.downgrade,'b1283aedf459'),(command.upgrade,'a01729dbe348')):
        fn(cfg,revision)
        with closing(sqlite3.connect(path)) as db:
            assert db.execute('PRAGMA quick_check').fetchone()==('ok',)
            assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
            assert db.execute('SELECT id,code,name FROM expense_categories ORDER BY id').fetchall()==before
    with closing(sqlite3.connect(path)) as db:
        assert len(db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'immutable_%'").fetchall())>=23
        db.execute("INSERT INTO invoice_issuer_profiles(identity,active) VALUES ('{}',1)");db.commit()
    with pytest.raises(RuntimeError,match='bloqueado'): command.downgrade(cfg,'b1283aedf459')


@pytest.mark.alembic_audit
def test_existing_private_billing_schema_is_adopted_without_row_changes(tmp_path,monkeypatch):
    path=tmp_path/'existing_billing.db'
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+path.as_posix())
    monkeypatch.setenv('ALEMBIC_REQUIRE_TEMPORARY_DATABASE','1')
    cfg=Config('alembic.ini');command.upgrade(cfg,'a01729dbe348')
    with closing(sqlite3.connect(path)) as db:
        db.execute("INSERT INTO invoice_issuer_profiles(identity,active) VALUES ('{}',1)")
        # Reproduce the private deployment's old marker, only in this test DB.
        db.execute("UPDATE alembic_version SET version_num='b1283aedf459'");db.commit()
        before=db.execute('SELECT * FROM invoice_issuer_profiles').fetchall()
        schema=db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
    command.upgrade(cfg,'a01729dbe348')
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT * FROM invoice_issuer_profiles').fetchall()==before
        assert db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()==schema
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        db.execute("UPDATE alembic_version SET version_num='b1283aedf459'")
        db.execute('ALTER TABLE invoice_issuer_profiles ADD COLUMN unexpected TEXT');db.commit()
    with pytest.raises(RuntimeError,match='no coincide'):command.upgrade(cfg,'a01729dbe348')
