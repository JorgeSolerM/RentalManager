from datetime import date,datetime
from uuid import uuid4
from pathlib import Path
import importlib.util
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.database.base import Base
from backend.models.payment import Payment
from backend.models.booking_charge import BookingCharge
from backend.services.payment_assignment_service import PaymentAssignmentService
from tests.integration.api.test_booking_finance_routes import make_finance_booking


def test_audit_migration_immutable_and_guarded_downgrade(tmp_path):
    path=Path('alembic/versions/d34a5c0f167b_payment_assignment_audit.py')
    spec=importlib.util.spec_from_file_location('assignment_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    assert migration.down_revision=='c2394bfe056a' and migration.depends_on is None
    engine=create_engine('sqlite:///'+(tmp_path/'assignment.db').as_posix())
    Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name!='payment_allocation_operations'])
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade();migration.downgrade();migration.upgrade()
    with Session(engine) as db:
        booking=make_finance_booking(db)
        p=Payment(booking_id=booking.id,amount=100,effective_date=date(2026,10,1),method='cash',direction='receipt',lifecycle='posted',posted_at=datetime(2026,10,1))
        c=BookingCharge(booking_id=booking.id,amount=100,type='rent',concept='Synthetic',due_date=date(2026,10,1),lifecycle='posted',posted_at=datetime(2026,10,1))
        db.add_all([p,c]);db.commit()
        s=PaymentAssignmentService();pairs=[(c.id,'50')];v=s.preview(db,booking.id,p.id,pairs)
        s.confirm(db,booking.id,p.id,pairs,request_key=str(uuid4()),expected=v['fingerprint'],confirmed=True)
    for sql in ['update payment_allocation_operations set amount=1','delete from payment_allocation_operations']:
        with engine.connect() as connection:
            with pytest.raises(IntegrityError):connection.execute(text(sql))
            connection.rollback()
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError,match='trazabilidad'):migration.downgrade()
        assert connection.execute(text('pragma quick_check')).fetchall()==[('ok',)]
        assert not connection.execute(text('pragma foreign_key_check')).fetchall()
    engine.dispose()
