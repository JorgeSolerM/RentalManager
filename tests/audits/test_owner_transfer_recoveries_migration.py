from pathlib import Path
from uuid import uuid4
import importlib.util
import pytest
from sqlalchemy import MetaData,create_engine,text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.database.base import Base
from tests.unit.test_owner_transfer_recoveries import sample,paid,register,extra,incidents,recoveries,recover,pay,bank_return


def test_additive_migration_guards_and_preservation(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('migration',Path('alembic/versions/39a0b257cd12_owner_transfer_recoveries.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.down_revision=='289fa146bc01' and m.depends_on is None
    metadata=MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name not in m.TABLES:table.to_metadata(metadata)
    engine=create_engine('sqlite:///'+(tmp_path/'migration.db').as_posix());metadata.create_all(engine)
    with engine.begin() as c:
        for action in ('update','delete'):c.execute(text(f"CREATE TRIGGER owner_payouts_immutable_{action} BEFORE {action.upper()} ON owner_payouts BEGIN SELECT RAISE(ABORT,'immutable'); END"))
        original=c.execute(text("select name,sql from sqlite_master where type='trigger'")).fetchall()
        with Operations.context(MigrationContext.configure(c)):m.upgrade();m.downgrade();m.upgrade()
        for name,sql in original:assert c.execute(text('select sql from sqlite_master where name=:n'),dict(n=name)).scalar()==sql
    with Session(engine) as db:
        data=sample.__wrapped__(db,monkeypatch);s,p,a=paid.__wrapped__(db,data)
        ret=bank_return(db,s,p,amount='10');i=register(db,s,p,amount='90')
        view=recoveries.link_preview(db,i.id,return_id=ret.id,reason='Synthetic documentary link')
        recoveries.link_return(db,i.id,return_id=ret.id,reason='Synthetic documentary link',expected=view['fingerprint'],request_key=str(uuid4()),confirmed=True)
        recover(db,i,a,amount='30')
        j=register(db,s,p,**extra(s,p,allocations={}));row=recover(db,j,a,amount='20',bank_transaction_id='MIGRATION-SECOND')
        view=incidents.attribution_preview(db,j.id,allocations={str(s.owner_id):'80'},reason='Synthetic source')
        incidents.attribute(db,j.id,allocations={str(s.owner_id):'80'},reason='Synthetic source',expected=view['fingerprint'],request_key=str(uuid4()),confirmed=True)
        view=recoveries.attribution_preview(db,row.id,reason='Synthetic recovered allocation')
        recoveries.attribute(db,row.id,allocations={},reason='Synthetic recovered allocation',expected=view['fingerprint'],request_key=str(uuid4()),confirmed=True)
        pay(db,s,a,amount='10')
        for table in [*m.TABLES,'owner_payouts']:
            assert db.execute(text('SELECT COUNT(*) FROM '+table)).scalar()>0
            for sql in ['DELETE FROM '+table,'UPDATE '+table+' SET id=id']:
                with pytest.raises(IntegrityError):db.execute(text(sql))
                db.rollback()
        cols=[r[1] for r in db.execute(text('pragma table_info(owner_transfer_recoveries)')) if r[1]!='id']
        expressions=["'different-key'" if c=='request_key' else c for c in cols]
        with pytest.raises(IntegrityError):db.execute(text('INSERT INTO owner_transfer_recoveries ('+','.join(cols)+') SELECT '+','.join(expressions)+' FROM owner_transfer_recoveries WHERE id=1'))
        db.rollback()
    with engine.begin() as c:
        with Operations.context(MigrationContext.configure(c)):
            with pytest.raises(RuntimeError):m.downgrade()
        assert c.execute(text('pragma quick_check')).fetchall()==[('ok',)] and not c.execute(text('pragma foreign_key_check')).fetchall()
    engine.dispose()
