from uuid import uuid4
from datetime import date
from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from sqlalchemy import select,func,event
from sqlalchemy.orm import Session
from backend.models.owner_settlement import Expense,ExpensePayment,ExpenseCategory,OwnerPayout
from backend.models.expense_correction import ExpensePaymentVoidOperation,ExpenseCorrectionOperation
from backend.services.expense_correction_service import ExpenseCorrectionService,record
from backend.services.expense_service import ExpenseService
from tests.unit.test_expense_service import expense,pay
from tests.unit.test_owner_settlement_service import sample,draft,preview,service as settlements

service=ExpenseCorrectionService()

def act(db,e,kind='void',payment_id=None,**values):
    args=dict(kind=kind,reason='Error sintético');args.update(values)
    view=service.preview(db,e.id,payment_id=payment_id,**args)
    return service.confirm(db,e.id,payment_id=payment_id,**args,request_key=str(uuid4()),expected=view['fingerprint'],confirmed=True)

def correction(e,amount):return dict(base_amount=amount,concept='Concepto corregido',category_id=e.category_id)

def test_unpaid_void_preserves_original(db_session,expense):
    before=record(expense);op=act(db_session,expense)
    assert expense.lifecycle=='void' and expense.voided_at
    assert op.before_state==before and op.after_state['total_amount']=='300.00'
    balance=service.expenses.balance(db_session,expense.id)
    assert balance.unpaid==0 and balance.paid==0 and balance.status=='void'
    assert db_session.scalar(select(func.count()).select_from(ExpensePayment))==0
    with pytest.raises(ValueError):pay(db_session,expense)

def test_void_payment_then_expense(db_session,expense):
    p=pay(db_session,expense,reference='SYNTHETIC-REF',notes='Nota sintética');before=record(p)
    with pytest.raises(ValueError,match='pagos efectivos'):act(db_session,expense)
    with pytest.raises(ValueError,match='salida real'):act(db_session,expense,'payment_void',p.id)
    op=act(db_session,expense,'payment_void',p.id,no_money_moved=True)
    assert p.lifecycle=='void' and op.before_state==before
    for field in before:
        if field not in ('lifecycle','voided_at'):assert record(p)[field]==before[field]
    assert service.expenses.balance(db_session,expense.id).unpaid==300
    assert len(service.expenses.payments(db_session,expense.id))==1
    with pytest.raises(ValueError):pay(db_session,expense,corrects_id=p.id,amount='50')
    act(db_session,expense)
    assert expense.lifecycle=='void' and len(service.history(db_session,expense.id))==2

@pytest.mark.parametrize('amount,paid,pending',[('350','100',250),('200','100',100),('400','300',100)])
def test_correct_partial_and_paid(db_session,expense,amount,paid,pending):
    p=pay(db_session,expense,amount=paid);original=record(p)
    op=act(db_session,expense,'correct',**correction(expense,amount))
    assert expense.id==op.expense_id and record(p)==original
    b=service.expenses.balance(db_session,expense.id);assert b.unpaid==pending and str(b.paid)==paid+'.00'
    assert db_session.scalar(select(func.count()).select_from(ExpensePayment))==1

def test_reduction_below_paid_and_real_payment_blocked(db_session,expense):
    p=pay(db_session,expense)
    with pytest.raises(ValueError,match='pagado'):act(db_session,expense,'correct',**correction(expense,'80'))
    with pytest.raises(ValueError,match='salida real'):act(db_session,expense,'payment_void',p.id,no_money_moved=False)
    assert p.lifecycle=='posted' and expense.total_amount==300

def test_refunded_zero_is_not_voidable(db_session,expense):
    p=pay(db_session,expense,amount='300');pay(db_session,expense,corrects_id=p.id,amount='300')
    assert service.expenses.balance(db_session,expense.id).paid==0
    for kind in ('void','correct'):
        with pytest.raises(ValueError,match='devoluciones'):act(db_session,expense,kind,**(correction(expense,'400') if kind=='correct' else {}))
    with pytest.raises(ValueError,match='devoluciones'):act(db_session,expense,'payment_void',p.id,no_money_moved=True)

def test_closed_one_coowner_blocks_all(db_session,sample):
    category=ExpenseCategory(code='correction-test',name='Prueba',active=True);db_session.add(category);db_session.commit()
    e=ExpenseService().create(db_session,property_id=sample['property'].id,category_id=category.id,expense_date=date(2026,9,1),concept='Prueba',base_amount='100',vat_rate='0',withholding_rate='0')
    p=pay(db_session,e,amount='100');closed=draft(db_session,sample,'a');settlements.close(db_session,closed.id,closed.fingerprint)
    snapshot=json.dumps(closed.snapshot,sort_keys=True)
    for kind,extra in [('void',{}),('correct',correction(e,'200')),('payment_void',{'payment_id':p.id,'no_money_moved':True})]:
        with pytest.raises(ValueError,match='liquidación cerrada'):act(db_session,e,kind,**extra)
    assert json.dumps(closed.snapshot,sort_keys=True)==snapshot
    assert db_session.scalar(select(func.count()).select_from(OwnerPayout))==0

def test_void_excluded_and_draft_becomes_stale(db_session,sample):
    category=ExpenseCategory(code='stale-test',name='Prueba',active=True);db_session.add(category);db_session.commit()
    e=ExpenseService().create(db_session,property_id=sample['property'].id,category_id=category.id,expense_date=date(2026,9,1),concept='Prueba',base_amount='100',vat_rate='0',withholding_rate='0')
    p=pay(db_session,e,amount='100');item=draft(db_session,sample)
    act(db_session,e,'payment_void',p.id,no_money_moved=True)
    with pytest.raises(ValueError,match='desactualizados'):settlements.close(db_session,item.id,item.fingerprint)
    assert not [r for r in preview(db_session,sample)['rows'] if r['kind']=='expense']

def test_preview_stale(db_session,expense):
    args=dict(kind='correct',reason='Error',**correction(expense,'400'))
    v=service.preview(db_session,expense.id,**args);pay(db_session,expense)
    with pytest.raises(ValueError,match='cambiado'):service.confirm(db_session,expense.id,**args,request_key=str(uuid4()),expected=v['fingerprint'],confirmed=True)

@pytest.mark.parametrize('kind',['void','payment_void','correct'])
def test_concurrent_idempotence(db_session,expense,kind):
    p=pay(db_session,expense) if kind=='payment_void' else None
    eid=expense.id;pid=p.id if p else None
    args=dict(kind=kind,reason='Error')
    if p:args['no_money_moved']=True
    if kind=='correct':args.update(correction(expense,'400'))
    v=service.preview(db_session,eid,payment_id=pid,**args);key=str(uuid4())
    def run(k):
        with Session(db_session.bind) as db:
            try:return service.confirm(db,eid,payment_id=pid,**args,request_key=k,expected=v['fingerprint'],confirmed=True).request_key
            except ValueError:return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(run,[key,key]))==[key,key]
    assert run(str(uuid4()))=='blocked'
    db_session.expire_all();assert len(service.history(db_session,eid))==1

@pytest.mark.parametrize('kind,model',[('correct',ExpenseCorrectionOperation),('payment_void',ExpensePaymentVoidOperation)])
def test_transaction_rollback(db_session,expense,kind,model):
    p=pay(db_session,expense) if kind=='payment_void' else None
    before=record(expense);pbefore=record(p) if p else None
    def fail(*args):raise RuntimeError('synthetic failure')
    event.listen(model,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError):act(db_session,expense,kind,p.id if p else None,**({'no_money_moved':True} if p else correction(expense,'400')))
    finally:event.remove(model,'before_insert',fail)
    db_session.expire_all();assert record(expense)==before
    if p:assert record(p)==pbefore
    assert not service.history(db_session,expense.id)

def test_unaudited_void_and_cross_expense(db_session,expense):
    p=pay(db_session,expense);p.lifecycle='void';db_session.commit()
    with pytest.raises(ValueError,match='auditoría'):act(db_session,expense)
    with pytest.raises(LookupError):service.form(db_session,expense.id,'payment_void',2147483647)

def test_category_tax_and_original_references(db_session,expense):
    expense.vat_rate=21;expense.withholding_rate=15;expense.vat_amount=63;expense.withholding_amount=45;expense.total_amount=318;expense.notes='Documento sintético';db_session.commit()
    category=ExpenseCategory(code='inactive',name='Histórica',active=False);db_session.add(category);db_session.commit()
    with pytest.raises(ValueError,match='inactiva'):act(db_session,expense,'correct',base_amount='400',concept='Nuevo',category_id=category.id)
    op=act(db_session,expense,'correct',**correction(expense,'400'))
    assert expense.total_amount==424 and expense.notes=='Documento sintético'
    assert op.before_state['notes']==op.after_state['notes']=='Documento sintético'
