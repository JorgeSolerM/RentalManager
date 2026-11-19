from uuid import uuid4
from datetime import date
import pytest
from sqlalchemy import select,func
from tests.unit.test_expense_service import expense,pay
from tests.unit.test_expense_corrections import sample,draft,settlements
from tests.integration.api.test_payment_correction_http import live_http,fields
from backend.models.owner_settlement import Expense,ExpensePayment,ExpenseCategory
from backend.models.expense_correction import ExpensePaymentVoidOperation,ExpenseCorrectionOperation
from backend.services.expense_correction_service import ExpenseCorrectionService
from backend.services.expense_service import ExpenseService


def preview_form(client,url,data):
    response=client.post(url+'/preview',data=data)
    assert response.status_code==200,response.text
    return fields(response).hidden

def test_real_http_void_payment_then_expense(live_http,db_session,expense):
    p=pay(db_session,expense);url=f'/expenses/{expense.id}/review'
    page=live_http.get(url+f'?kind=payment_void&payment_id={p.id}')
    assert page.status_code==200 and 'salida real' in page.text and 'amount' not in fields(page).names
    values=dict(kind='payment_void',payment_id=str(p.id),reason='Registro sin pago real')
    assert live_http.post(url+'/preview',data=values).status_code==409
    payload=preview_form(live_http,url,values|{'no_money_moved':'yes'})
    assert 'amount' not in payload
    assert live_http.post(url+'/confirm',data=payload).status_code==409
    assert live_http.post(url+'/confirm',data=payload|{'confirmed':'yes'}).status_code==409
    payload.update(confirmed='yes',no_money_moved='yes')
    assert live_http.post(url+'/confirm',data=payload).status_code==303
    assert live_http.post(url+'/confirm',data=payload).status_code==303
    assert p.lifecycle=='void'
    payload=preview_form(live_http,url,dict(kind='void',reason='Gasto duplicado'))
    assert live_http.post(url+'/confirm',data=payload|{'confirmed':'yes'}).status_code==303
    assert expense.lifecycle=='void'
    assert db_session.scalar(select(func.count()).select_from(ExpensePayment))==1
    assert db_session.scalar(select(func.count()).select_from(ExpensePaymentVoidOperation))==1
    assert db_session.scalar(select(func.count()).select_from(ExpenseCorrectionOperation))==1
    page=live_http.get(f'/expenses/{expense.id}')
    assert page.status_code==200 and 'Registro sin pago real' in page.text and 'Gasto duplicado' in page.text
    assert 'Registrar pago / devolución' not in page.text
    assert live_http.get('/expenses').status_code==200

def test_http_correction(client,db_session,expense):
    p=pay(db_session,expense);url=f'/expenses/{expense.id}/review'
    assert client.get(url).status_code==200
    values=dict(kind='correct',reason='Importe incorrecto',base_amount='200',concept='Concepto revisado',category_id=str(expense.category_id))
    payload=preview_form(client,url,values)
    assert client.post(url+'/confirm',data=payload|{'confirmed':'yes'},follow_redirects=False).status_code==303
    assert expense.total_amount==200 and p.amount==100
    assert ExpenseService().balance(db_session,expense.id).unpaid==100

@pytest.mark.parametrize('kind',['void','correct','payment_void'])
@pytest.mark.parametrize('action',['preview','confirm'])
def test_http_absent_fields(client,db_session,expense,kind,action):
    p=pay(db_session,expense)
    values={'kind':kind,'payment_id':str(p.id)}
    response=client.post(f'/expenses/{expense.id}/review/{action}',data=values)
    assert response.status_code==409
    assert expense.lifecycle=='posted' and p.lifecycle=='posted'

def test_http_invalid_and_missing_entities(client,expense):
    root=f'/expenses/{expense.id}/review'
    for values in [{},{'kind':'wrong'},{'kind':'payment_void','payment_id':'wrong'},{'kind':'payment_void','payment_id':'999999','reason':'Error','no_money_moved':'yes'}]:
        assert client.post(root+'/preview',data=values).status_code in (400,404,409)
    assert client.get('/expenses/999999/review?kind=void').status_code==404
    assert client.post('/expenses/999999/review/preview',data={'kind':'void','reason':'Error'}).status_code==404

def test_http_closed_and_refund_blockers(client,db_session,sample):
    cat=ExpenseCategory(code='http-block',name='Prueba',active=True);db_session.add(cat);db_session.commit()
    e=ExpenseService().create(db_session,property_id=sample['property'].id,category_id=cat.id,expense_date=date(2026,9,1),concept='Prueba',base_amount='100',vat_rate='0',withholding_rate='0')
    p=pay(db_session,e);item=draft(db_session,sample);settlements.close(db_session,item.id,item.fingerprint)
    root=f'/expenses/{e.id}/review'
    page=client.get(root+f'?kind=payment_void&payment_id={p.id}')
    assert page.status_code==200 and 'liquidación cerrada' in page.text
    assert 'Revisar impacto</button>' not in page.text
    assert client.post(root+'/preview',data={'kind':'payment_void','payment_id':p.id,'reason':'Error','no_money_moved':'yes'}).status_code==409

def test_public_expense_corrections_not_exposed():
    from fastapi.testclient import TestClient
    from backend.public.app_factory import create_public_app
    with TestClient(create_public_app()) as client:
        assert client.get('/expenses/1/review').status_code in (403,404)
        assert client.post('/expenses/1/review/confirm',data={'confirmed':'yes'}).status_code in (403,404,405)
