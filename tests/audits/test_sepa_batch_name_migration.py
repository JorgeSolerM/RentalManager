import sqlite3
from contextlib import closing
from alembic import command
from alembic.config import Config
import pytest


@pytest.mark.alembic_audit
def test_batch_name_upgrade_downgrade_reupgrade(tmp_path,monkeypatch):
    path=tmp_path/'batch_name.db'
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+path.as_posix())
    monkeypatch.setenv('ALEMBIC_REQUIRE_TEMPORARY_DATABASE','1')
    cfg=Config('alembic.ini')
    command.upgrade(cfg,'a9c1e3f5b782')
    with closing(sqlite3.connect(path)) as db:
        db.execute("insert into sepa_batches(reference,request_key,period,requested_collection_date,status) values('TEST-REF','TEST-KEY','2026-09-01','2026-09-10','prepared')")
        db.commit()
    for operation,revision in [(command.upgrade,'bac2e4f6d893'),(command.downgrade,'a9c1e3f5b782'),(command.upgrade,'bac2e4f6d893')]:
        operation(cfg,revision)
        with closing(sqlite3.connect(path)) as db:
            assert db.execute('pragma quick_check').fetchone()==('ok',)
            assert db.execute('pragma foreign_key_check').fetchall()==[]
            assert db.execute('select reference from sepa_batches').fetchall()==[('TEST-REF',)]
            if revision=='bac2e4f6d893':assert db.execute('select name from sepa_batches').fetchall()==[(None,)]
