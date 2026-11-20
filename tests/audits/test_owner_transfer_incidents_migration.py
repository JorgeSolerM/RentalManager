from pathlib import Path
import importlib.util
import pytest
from sqlalchemy import MetaData,create_engine,text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.database.base import Base
from tests.unit.test_owner_transfer_incidents import sample,paid,register,extra

def test_migration_immutable_and_guards(tmp_path,monkeypatch):
    spec=importlib.util.spec_from_file_location('migration',Path('alembic/versions/289fa146bc01_owner_transfer_incidents.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.down_revision=='178e9035abf0' and m.depends_on is None
    metadata=MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name not in m.TABLES:table.to_metadata(metadata)
    engine=create_engine('sqlite:///'+(tmp_path/'migration.db').as_posix());metadata.create_all(engine)
    with engine.begin() as c:
        for action in ('update','delete'):c.execute(text(f"CREATE TRIGGER owner_payouts_immutable_{action} BEFORE {action.upper()} ON owner_payouts BEGIN SELECT RAISE(ABORT,'immutable'); END"))
        original=c.execute(text("select name,sql from sqlite_master where type='trigger' order by name")).fetchall()
        with Operations.context(MigrationContext.configure(c)):m.upgrade();m.downgrade();m.upgrade()
        for name,sql in original:assert c.execute(text('select sql from sqlite_master where name=:n'),dict(n=name)).scalar()==sql
    with Session(engine) as db:
        data=sample.__wrapped__(db,monkeypatch);s,p,a=paid.__wrapped__(db,data)
        register(db,s,p);register(db,s,p,**extra(s,p))
        for table in ['owner_payouts',*m.TABLES]:
            for statement in ['DELETE FROM '+table,'UPDATE '+table+' SET '+('request_key=request_key' if table=='owner_transfer_incident_operations' else 'id=id')]:
                with pytest.raises(IntegrityError):db.execute(text(statement))
                db.rollback()
    with engine.begin() as c:
        with Operations.context(MigrationContext.configure(c)):
            with pytest.raises(RuntimeError):m.downgrade()
        assert c.execute(text('pragma quick_check')).fetchall()==[('ok',)]
        assert not c.execute(text('pragma foreign_key_check')).fetchall()
    engine.dispose()
