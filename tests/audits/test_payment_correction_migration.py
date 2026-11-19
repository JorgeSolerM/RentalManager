from pathlib import Path
import importlib.util
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.database.base import Base
from tests.integration.api.test_booking_finance_routes import make_finance_booking
from backend.models import Payment, BookingCharge, PaymentAllocation
from backend.models.owner_settlement import PaymentCustody
from backend.services.payment_correction_service import PaymentCorrectionService
from datetime import date,datetime
from uuid import uuid4

def test_migration_guards(tmp_path):
    spec=importlib.util.spec_from_file_location('correction_migration',Path('alembic/versions/e45b6d10278c_payment_correction_audit.py'))
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    assert migration.down_revision=='d34a5c0f167b' and migration.depends_on is None
    engine=create_engine('sqlite:///'+(tmp_path/'correction.db').as_posix())
    Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name!='payment_correction_operations'])
    with engine.begin() as con:
        with Operations.context(MigrationContext.configure(con)):
            migration.upgrade();migration.downgrade();migration.upgrade()
    with Session(engine) as db:
        b=make_finance_booking(db)
        p=Payment(booking_id=b.id,amount=100,effective_date=date(2026,10,1),method='cash',direction='receipt',lifecycle='posted',posted_at=datetime(2026,10,1))
        c=BookingCharge(booking_id=b.id,amount=100,type='rent',concept='Synthetic',due_date=date(2026,10,1),lifecycle='posted',posted_at=datetime(2026,10,1))
        db.add_all([p,c]);db.flush()
        db.add_all([PaymentCustody(payment_id=p.id,actor='manager',amount=100),PaymentAllocation(payment_id=p.id,charge_id=c.id,amount=50)]);db.commit()
        s=PaymentCorrectionService();v=s.preview(db,b.id,p.id,kind='void',reason='Error')
        s.confirm(db,b.id,p.id,kind='void',reason='Error',request_key=str(uuid4()),expected=v['fingerprint'],confirmed=True)
        pid=p.id
    for sql in ['update payment_correction_operations set reason="other"','delete from payment_correction_operations',f'update payments set lifecycle="posted" where id={pid}','update payment_allocations set amount=20','delete from payment_allocations']:
        with engine.connect() as con:
            with pytest.raises(IntegrityError):con.execute(text(sql))
            con.rollback()
    with engine.begin() as con:
        with Operations.context(MigrationContext.configure(con)):
            with pytest.raises(RuntimeError):migration.downgrade()
        assert con.execute(text('pragma quick_check')).fetchall()==[('ok',)]
        assert not con.execute(text('pragma foreign_key_check')).fetchall()
    engine.dispose()
