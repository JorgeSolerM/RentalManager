from pathlib import Path
import importlib.util
import pytest
from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.database.base import Base
from tests.unit.test_owner_loss_compensations import sample,paid,setup,confirm,application_values

def test_additive_immutable_limits_and_owner_payout_guards(tmp_path,monkeypatch):
    path=Path('alembic/versions/5bc2d479ef34_owner_loss_compensations.py')
    spec=importlib.util.spec_from_file_location('compensation_migration',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    assert m.down_revision=='4ab1c368de23' and m.depends_on is None
    metadata=MetaData()
    for table in Base.metadata.sorted_tables:
        if not table.name.startswith('owner_loss_compensation_'):table.to_metadata(metadata)
    engine=create_engine('sqlite:///'+(tmp_path/'migration.db').as_posix());metadata.create_all(engine)
    with engine.begin() as c:
        for action in ('update','delete'):c.execute(text(f"CREATE TRIGGER owner_payouts_immutable_{action} BEFORE {action.upper()} ON owner_payouts BEGIN SELECT RAISE(ABORT,'immutable'); END"))
        original=c.execute(text("select name,sql from sqlite_master where type='trigger'")).fetchall()
        with Operations.context(MigrationContext.configure(c)):m.upgrade();m.downgrade();m.upgrade()
        for name,sql in original:assert c.execute(text('select sql from sqlite_master where name=:n'),dict(n=name)).scalar()==sql
    with Session(engine) as db:
        data=sample.__wrapped__(db,monkeypatch);s,p,bank=paid.__wrapped__(db,data);i,loss,a=setup(db,s,p)
        confirm(db,i,application_values(s,a,amount='100'))
        for table in ('owner_loss_compensation_authorizations','owner_loss_compensation_applications'):
            for sql in [f'UPDATE {table} SET amount=1',f'DELETE FROM {table}']:
                with pytest.raises(IntegrityError):db.execute(text(sql))
                db.rollback()
        table='owner_loss_compensation_applications'
        cols=[r[1] for r in db.execute(text('pragma table_info('+table+')')) if r[1]!='id']
        expressions=["'different-key'" if c=='request_key' else c for c in cols]
        with pytest.raises(IntegrityError):db.execute(text(f'INSERT INTO {table} ('+','.join(cols)+') SELECT '+','.join(expressions)+f' FROM {table}'))
        db.rollback()
    with engine.begin() as c:
        with Operations.context(MigrationContext.configure(c)):
            with pytest.raises(RuntimeError):m.downgrade()
        assert c.execute(text('pragma quick_check')).fetchall()==[('ok',)] and not c.execute(text('pragma foreign_key_check')).fetchall()
        for name,sql in original:assert c.execute(text('select sql from sqlite_master where name=:n'),dict(n=name)).scalar()==sql
    engine.dispose()


def test_directed_upgrade_preserves_synthetic_closed_history(tmp_path, monkeypatch):
    from datetime import date, datetime
    from alembic import command
    from alembic.config import Config
    from backend.models.owner import Owner
    from backend.models.owner_settlement import OwnerSettlement
    database = (tmp_path / 'pre43-synthetic.db').resolve()
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        if not table.name.startswith('owner_loss_compensation_'):
            table.to_metadata(metadata)
    engine = create_engine('sqlite:///' + database.as_posix())
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(Owner.__table__.insert().values(id=901, legal_name='Synthetic preserved owner'))
        connection.execute(OwnerSettlement.__table__.insert().values(id=901, owner_id=901,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1), status='closed',
            closed_at=datetime(2026, 2, 1), selection={}, snapshot={'totals': {'payout_due': '125.00'}},
            fingerprint='synthetic-preserved', request_key='synthetic-preserved'))
        # Explicit fixture revision; never infer or stamp a real database.
        connection.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
        connection.execute(text("INSERT INTO alembic_version VALUES ('4ab1c368de23')"))
        before = {table.name: connection.execute(table.select()).fetchall() for table in metadata.sorted_tables}
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + database.as_posix())
    monkeypatch.setenv('ALEMBIC_REQUIRE_TEMPORARY_DATABASE', '1')
    command.upgrade(Config('alembic.ini'), '5bc2d479ef34')
    with engine.connect() as connection:
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalars().all() == ['5bc2d479ef34']
        assert before == {table.name: connection.execute(table.select()).fetchall() for table in metadata.sorted_tables}
        assert connection.execute(text('PRAGMA quick_check')).fetchall() == [('ok',)]
        assert connection.execute(text('PRAGMA foreign_key_check')).fetchall() == []
        assert len(connection.execute(text("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'loss_comp_%'")).fetchall()) == 6
    engine.dispose()
