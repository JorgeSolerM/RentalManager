from pathlib import Path
import importlib.util
import pytest
from sqlalchemy import MetaData,create_engine,text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.database.base import Base
from tests.unit.test_owner_transfer_losses import sample,paid,register,recognize,losses,values

def test_additive_migration_and_immutable_history(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('loss_migration',Path('alembic/versions/4ab1c368de23_owner_transfer_losses.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.down_revision=='39a0b257cd12' and m.depends_on is None
    metadata=MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name!='owner_transfer_regularizations' and not table.name.startswith('owner_loss_compensation_'):table.to_metadata(metadata)
    engine=create_engine('sqlite:///'+(tmp_path/'migration.db').as_posix());metadata.create_all(engine)
    with engine.begin() as c:
        for action in ('update','delete'):c.execute(text(f"CREATE TRIGGER owner_payouts_immutable_{action} BEFORE {action.upper()} ON owner_payouts BEGIN SELECT RAISE(ABORT,'immutable'); END"))
        original=c.execute(text("select name,sql from sqlite_master where type='trigger'")).fetchall()
        with Operations.context(MigrationContext.configure(c)):m.upgrade();m.downgrade();m.upgrade()
        for name,sql in original:assert c.execute(text('select sql from sqlite_master where name=:n'),dict(n=name)).scalar()==sql
    # The historical migration is tested above; current services also read the
    # newer compensation projection. Supply its empty tables for this fixture.
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        data=sample.__wrapped__(db,monkeypatch);s,p,a=paid.__wrapped__(db,data);i=register(db,s,p);row=recognize(db,i,amount='100')
        for sql in ['UPDATE owner_transfer_regularizations SET amount=1','DELETE FROM owner_transfer_regularizations']:
            with pytest.raises(IntegrityError):db.execute(text(sql))
            db.rollback()
        cols=[r[1] for r in db.execute(text('pragma table_info(owner_transfer_regularizations)')) if r[1]!='id']
        expressions=["'different-key'" if c in ('request_key','recognition_key') else c for c in cols]
        with pytest.raises(IntegrityError):db.execute(text('INSERT INTO owner_transfer_regularizations ('+','.join(cols)+') SELECT '+','.join(expressions)+' FROM owner_transfer_regularizations'))
        db.rollback()
    with engine.begin() as c:
        with Operations.context(MigrationContext.configure(c)):
            with pytest.raises(RuntimeError):m.downgrade()
        assert c.execute(text('pragma quick_check')).fetchall()==[('ok',)] and not c.execute(text('pragma foreign_key_check')).fetchall()
    engine.dispose()
