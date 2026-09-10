import sqlite3
from contextlib import closing
from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from tests.integration.api.test_sepa_collections import scenario, create, COLLECTION


@pytest.mark.alembic_audit
def test_returns_migration_roundtrip_preserves_existing_instructions(tmp_path,monkeypatch):
    path=tmp_path/'returns_roundtrip.db'
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+path.as_posix())
    monkeypatch.setenv('ALEMBIC_REQUIRE_TEMPORARY_DATABASE','1')
    cfg=Config('alembic.ini')
    command.upgrade(cfg,'head')
    engine=create_engine('sqlite:///'+path.as_posix())
    with Session(engine,autoflush=False) as db:
        data=scenario.__wrapped__(db,tmp_path,monkeypatch)
        batch=create(db,data)
        data[0].export(db,batch.id);data[0].present(db,batch.id)
    engine.dispose()
    # Current ORM includes later administrative metadata; remove that revision
    # before auditing the original returns migration in isolation.
    command.downgrade(cfg,'a9c1e3f5b782')
    counts={}
    for operation,revision in [(command.downgrade,'f8b0d2e4a671'),(command.upgrade,'a9c1e3f5b782')]:
        operation(cfg,revision)
        with closing(sqlite3.connect(path)) as db:
            current={t:db.execute('select count(*) from '+t).fetchone()[0] for t in ('bookings','booking_charges','sepa_batches','sepa_debits','sepa_debit_charge_allocations','sepa_export_artifacts','payments')}
            if counts: assert counts==current
            counts=current
            assert db.execute('pragma quick_check').fetchone()==('ok',)
            assert not db.execute('pragma foreign_key_check').fetchall()
            assert db.execute('select status from sepa_debits').fetchone()==('presented',)
            if revision=='a9c1e3f5b782':
                assert db.execute('select return_payment_id,returned_on,cancelled_at from sepa_debits').fetchone()==(None,None,None)
                assert db.execute('select count(*) from payment_registrations').fetchone()==(0,)
    command.upgrade(cfg,'head')
    engine=create_engine('sqlite:///'+path.as_posix())
    with Session(engine,autoflush=False) as db:
        data[0].collect(db,1,[1],COLLECTION)
        data[0].return_debits(db,1,[1],COLLECTION)
    engine.dispose()
    with pytest.raises(RuntimeError,match='Downgrade blocked'):
        command.downgrade(cfg,'f8b0d2e4a671')
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('select status from sepa_debits').fetchone()==('returned',)
        assert db.execute('pragma quick_check').fetchone()==('ok',)
        assert not db.execute('pragma foreign_key_check').fetchall()
