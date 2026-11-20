from pathlib import Path
import importlib.util
import pytest
from sqlalchemy import MetaData,create_engine,text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.database.base import Base
from backend.models.owner_payout_correction import OwnerPayoutCorrectionOperation
from tests.unit.test_owner_payout_corrections import service
from uuid import uuid4
from tests.unit.test_owner_payout_returns import sample,paid,register


def test_append_only_returns_and_preserved_payout_triggers(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('migration',Path('alembic/versions/178e9035abf0_owner_payout_returns.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.down_revision=='067d8f3249ae' and m.depends_on is None
    metadata=MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name!=m.TABLE:table.to_metadata(metadata)
    engine=create_engine('sqlite:///'+(tmp_path/'migration.db').as_posix());metadata.create_all(engine)
    with engine.begin() as c:
        for event in ('update','delete'):
            c.execute(text(f"CREATE TRIGGER owner_payouts_immutable_{event} BEFORE {event.upper()} ON owner_payouts BEGIN SELECT RAISE(ABORT,'immutable'); END"))
        original=c.execute(text("select name,sql from sqlite_master where type='trigger' order by name")).fetchall()
        with Operations.context(MigrationContext.configure(c)):m.upgrade();m.downgrade();m.upgrade()
        for name,sql in original:assert c.execute(text('select sql from sqlite_master where name=:name'),{'name':name}).scalar()==sql
    with Session(engine) as db:
        data=sample.__wrapped__(db,monkeypatch);s,p,a=paid.__wrapped__(db,data);register(db,s,p)
        for statement in ["update owner_payouts set amount=1",'delete from owner_payouts',"update owner_payout_returns set reason='x'",'delete from owner_payout_returns']:
            with pytest.raises(IntegrityError):db.execute(text(statement))
            db.rollback()
        # Database guards independently reject bypassing the service.
        bad=OwnerPayoutCorrectionOperation(request_key=str(uuid4()),original_payout_id=p.id,kind='void',reason='synthetic',no_transfer=True,before_state={},after_state={},impact={},fingerprint='x',reviewed_state='x')
        db.add(bad)
        with pytest.raises(IntegrityError,match='payout_has_received_returns'):db.flush()
        db.rollback()
        second=service.payout(db,s.id,amount='10',effective_date=p.effective_date,bank_account_id=a.id,method='bank_transfer',request_key=str(uuid4()))
        with pytest.raises(IntegrityError,match='invalid_payout_return'):
            db.execute(text("INSERT INTO owner_payout_returns (payout_id,transfer_root_id,amount,effective_date,bank_reference,receiving_account_hash,receiving_account_suffix,reason,received,request_key,dedupe_key,fingerprint,reviewed_state,impact) SELECT payout_id,:wrong,1,effective_date,bank_reference,receiving_account_hash,receiving_account_suffix,reason,received,:key,:key,fingerprint,reviewed_state,impact FROM owner_payout_returns LIMIT 1"),dict(wrong=second.id,key=str(uuid4())))
        db.rollback()
    with engine.begin() as c:
        with Operations.context(MigrationContext.configure(c)):
            with pytest.raises(RuntimeError):m.downgrade()
        assert c.execute(text('pragma quick_check')).fetchall()==[('ok',)]
        assert not c.execute(text('pragma foreign_key_check')).fetchall()
    engine.dispose()
