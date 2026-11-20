from pathlib import Path
import importlib.util
import pytest
from sqlalchemy import MetaData,create_engine,text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.database.base import Base
from tests.unit.test_owner_payout_corrections import sample,paid,args,apply
from backend.models.owner_settlement import OwnerPayout


def test_append_only_and_legacy_triggers(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('migration',Path('alembic/versions/067d8f3249ae_owner_payout_corrections.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.down_revision=='f56c7e21389d' and m.depends_on is None
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
        setup=sample.__wrapped__(db,monkeypatch);s,p,a=paid.__wrapped__(db,setup)
        before=p.amount
        op=apply(db,s,p,**args())
        assert p.amount==before and db.get(OwnerPayout,op.replacement_payout_id).amount==150
        for statement in ["update owner_payouts set amount=1",'delete from owner_payouts',"update owner_payout_correction_operations set reason='x'",'delete from owner_payout_correction_operations']:
            with pytest.raises(IntegrityError):db.execute(text(statement))
            db.rollback()
    with engine.begin() as c:
        with Operations.context(MigrationContext.configure(c)):
            with pytest.raises(RuntimeError):m.downgrade()
        assert c.execute(text('pragma quick_check')).fetchall()==[('ok',)]
        assert not c.execute(text('pragma foreign_key_check')).fetchall()
    engine.dispose()
