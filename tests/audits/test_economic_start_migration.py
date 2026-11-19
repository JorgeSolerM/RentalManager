import sqlite3
from contextlib import closing
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
import pytest
from tests.integration.api.test_booking_finance_routes import make_finance_booking

@pytest.mark.alembic_audit
def test_economic_start_migration_without_fiscal_revision(tmp_path,monkeypatch):
    path=tmp_path/'economic_start.db'
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+path.as_posix())
    monkeypatch.setenv('ALEMBIC_REQUIRE_TEMPORARY_DATABASE','1')
    cfg=Config('alembic.ini')
    command.upgrade(cfg,'b1283aedf459')
    for action,revision in ((command.upgrade,'c2394bfe056a'),(command.downgrade,'b1283aedf459'),(command.upgrade,'c2394bfe056a')):
        action(cfg,revision)
        with closing(sqlite3.connect(path)) as db:
            assert db.execute('pragma quick_check').fetchone()==('ok',)
            assert not db.execute('pragma foreign_key_check').fetchall()
            assert db.execute('select version_num from alembic_version').fetchone()==(revision,)
            assert not db.execute("select name from sqlite_master where name='management_fee_invoices'").fetchall()
    engine=create_engine('sqlite:///'+path.as_posix())
    with Session(engine) as session:
        bid=make_finance_booking(session).id
    engine.dispose()
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('select economic_management_start,economic_management_start_configured_at from bookings where id=?',(bid,)).fetchone()==(None,None)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("update bookings set economic_management_start='2026-10-02' where id=?",(bid,))
        db.rollback()
        db.execute("update bookings set economic_management_start='2026-10-01' where id=?",(bid,));db.commit()
    with pytest.raises(RuntimeError,match='configuración'):
        command.downgrade(cfg,'b1283aedf459')
