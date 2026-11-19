from pathlib import Path
from datetime import date
from uuid import uuid4
import importlib.util
import pytest
from sqlalchemy import MetaData,create_engine,text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from backend.database.base import Base
from backend.models import Property
from backend.models.owner_settlement import ExpenseCategory
from backend.services.expense_service import ExpenseService
from backend.services.expense_correction_service import ExpenseCorrectionService

def test_additive_migration_and_audit_guards(tmp_path):
    spec=importlib.util.spec_from_file_location('expense_migration',Path('alembic/versions/f56c7e21389d_expense_corrections.py'))
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    assert migration.down_revision=='e45b6d10278c' and migration.depends_on is None
    old=MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name not in migration.TABLES:table.to_metadata(old)
    for name,cols in [('expenses',['voided_at']),('expense_payments',['lifecycle','voided_at'])]:
        table=old.tables[name]
        for constraint in list(table.constraints):
            if constraint.name=='ck_expense_payment_lifecycle':table.constraints.remove(constraint)
        for col in cols:table._columns.remove(table.c[col])
    engine=create_engine('sqlite:///'+(tmp_path/'audit.db').as_posix());old.create_all(engine)
    with engine.begin() as con:
        con.execute(text("CREATE TRIGGER expense_payments_immutable_update BEFORE UPDATE ON expense_payments BEGIN SELECT RAISE(ABORT,'Financial history is immutable'); END"))
        with Operations.context(MigrationContext.configure(con)):
            migration.upgrade();migration.downgrade();migration.upgrade()
    with Session(engine) as db:
        prop=Property(name='Finca sintética',address='Calle prueba',city='Elche',owner='');cat=ExpenseCategory(code='test',name='Prueba',active=True)
        db.add_all([prop,cat]);db.commit()
        e=ExpenseService().create(db,property_id=prop.id,category_id=cat.id,expense_date=date(2026,9,1),concept='Prueba',base_amount='300',vat_rate='0',withholding_rate='0')
        pay=ExpenseService().pay(db,e.id,effective_date=date(2026,9,1),amount='100',paid_by='manager',request_key=str(uuid4()))
        # Legacy immutability still protects the original cash facts before any void.
        with pytest.raises(IntegrityError):
            db.execute(text("update expense_payments set amount=99 where id=:id"),{'id':pay.id})
        db.rollback()
        service=ExpenseCorrectionService()
        for kind,pid,extra in [('payment_void',pay.id,{'no_money_moved':True}),('void',None,{})]:
            args=dict(kind=kind,reason='Prueba sintética',**extra);view=service.preview(db,e.id,payment_id=pid,**args)
            service.confirm(db,e.id,payment_id=pid,**args,request_key=str(uuid4()),expected=view['fingerprint'],confirmed=True)
    for sql in ["update expense_payments set lifecycle='posted'", "delete from expense_payments", "update expenses set lifecycle='posted'", "delete from expenses", "update expense_payment_void_operations set reason='changed'", "delete from expense_payment_void_operations", "update expense_correction_operations set reason='changed'", "delete from expense_correction_operations"]:
        with engine.connect() as con:
            with pytest.raises(IntegrityError):con.execute(text(sql))
            con.rollback()
    with engine.begin() as con:
        with Operations.context(MigrationContext.configure(con)):
            with pytest.raises(RuntimeError):migration.downgrade()
        assert con.execute(text('pragma quick_check')).fetchall()==[('ok',)]
        assert not con.execute(text('pragma foreign_key_check')).fetchall()
    engine.dispose()
