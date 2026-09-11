from datetime import date
from decimal import Decimal as D
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from backend.models import Owner,Property,PropertyOwnership
from backend.models.provider import Provider
from backend.models.owner_settlement import Expense,ExpenseCategory,ExpensePayment,OwnerSettlementLine
from backend.services.provider_service import ProviderService
from backend.services.expense_service import ExpenseService
from backend.services.owner_settlement_service import OwnerSettlementService


@pytest.fixture
def setup(db_session,monkeypatch):
    monkeypatch.setattr('backend.services.expense_service.business_today',lambda:date(2026,9,30))
    prop=Property(name='Finca de prueba',address='Dirección sintética',city='Elche',owner='')
    a=Owner(legal_name='Titular A');b=Owner(legal_name='Titular B')
    category=ExpenseCategory(code='repair',name='Reparaciones',active=True)
    db_session.add_all([prop,a,b,category]);db_session.flush()
    for owner in (a,b): db_session.add(PropertyOwnership(property_id=prop.id,owner_id=owner.id,ownership_percentage=D('50'),active=True))
    db_session.commit()
    return prop,a,b,category


def values(setup,**extra):
    prop,a,b,category=setup
    return dict(property_id=prop.id,category_id=category.id,expense_date=date(2026,9,1),concept='Gasto sintético',
        base_amount='100',vat_rate='0',withholding_rate='0',**extra)


def test_provider_lifecycle_history_and_bank_privacy(db_session,setup,client):
    service=ProviderService()
    p=service.save(db_session,legal_name='Proveedor sintético',iban='es91 2100 0418 4502 0005 1332',default_expense_category_id=setup[3].id)
    assert p.tax_id is None and p.iban=='ES9121000418450200051332'
    e=ExpenseService().create(db_session,**values(setup,provider_id=p.id))
    assert e.provider_id==p.id and 'iban' not in e.provider_snapshot
    old=dict(e.provider_snapshot)
    service.save(db_session,p.id,legal_name='Nombre actualizado',tax_id='TEST',iban='GB82WEST12345698765432')
    service.set_active(db_session,p.id,False)
    db_session.refresh(e)
    assert e.provider_id==p.id and e.provider_snapshot==old
    assert p not in service.list(db_session,active_only=True)
    with pytest.raises(ValueError,match='no disponible'):
        ExpenseService().create(db_session,**values(setup,provider_id=p.id))
    with pytest.raises(ValueError,match='desactivarlo'):
        service.delete(db_session,p.id)
    service.set_active(db_session,p.id,True)
    assert service.list(db_session,'actualizado')[0].id==p.id
    assert client.get(f'/providers/{p.id}').status_code==200
    assert p.iban not in client.get(f'/providers/{p.id}').text
    assert p.iban not in client.get('/providers').text
    assert p.iban in client.get(f'/providers/{p.id}/edit').text
    assert client.get('/providers?q=actualizado').status_code==200
    with pytest.raises(ValueError,match='IBAN'):
        service.save(db_session,legal_name='Otro',iban='ES0000000000000000000000')
    assert db_session.scalar(select(func.count()).select_from(Provider))==1


def test_provider_nullable_and_ui_routes(db_session,setup,client):
    e=ExpenseService().create(db_session,**values(setup))
    assert e.provider_id is None
    response=client.post('/providers/new',data={'legal_name':'Nuevo proveedor','active':'1'},follow_redirects=False)
    assert response.status_code==303
    assert client.get(response.headers['location']).status_code==200
    quick=client.post('/providers/quick',data={'legal_name':'Proveedor rápido','default_expense_category_id':setup[3].id})
    assert quick.status_code==200 and quick.json()['category_id']==setup[3].id
    page=client.get('/expenses/new').text
    assert 'data-category="'+str(setup[3].id)+'"' in page
    assert 'data-specific-owner hidden' in page and 'name="owner_id" disabled' in page
    assert 'name="supplier"' not in page and '+ Nuevo proveedor' in page
    assert '/providers' in client.get('/settings/').text
    assert 'provider_snapshot' not in page
    from backend.public.app_factory import create_public_app
    from fastapi.testclient import TestClient
    with TestClient(create_public_app()) as public:
        assert public.get('/providers').status_code==404
        assert public.get('/providers/1').status_code==404


@pytest.mark.parametrize('specific,payer',[ (False,'manager'),(False,'owner'),(True,'manager') ])
def test_single_property_expense_split_custody_and_consumption(db_session,setup,specific,payer):
    prop,a,b,category=setup
    es=ExpenseService();ss=OwnerSettlementService()
    e=es.create(db_session,**values(setup,owner_id=a.id if specific else None))
    payment=es.pay(db_session,e.id,effective_date=date(2026,9,10),amount='100',paid_by=payer,
        paid_by_owner_id=a.id if payer=='owner' else None,request_key=str(uuid4()))
    assert e.owner_id==(a.id if specific else None) and payment.paid_by==payer
    for owner,expected in ((a,'100' if specific else '50'),(b,'0' if specific else '50')):
        v=ss.preview(db_session,owner.id,date(2026,9,1),date(2026,10,1),[prop.id])
        assert not v['errors'] and D(v['totals']['expenses'])==D(expected)
        assert D(v['totals']['manager_credit'])==(D(expected) if payer=='manager' else D('0'))
        if D(expected):
            draft=ss.save_draft(db_session,owner_id=owner.id,start=date(2026,9,1),end=date(2026,10,1),property_ids=[prop.id],excluded=[],expected=v['fingerprint'],request_key=str(uuid4()))
            ss.close(db_session,draft.id,draft.fingerprint)
            assert D(ss.preview(db_session,owner.id,date(2026,9,1),date(2026,10,1),[prop.id])['totals']['expenses'])==0
    assert es.balance(db_session,e.id).settled==D('100')


def test_incomplete_ownership_registers_but_does_not_settle(db_session,setup,client):
    prop,a,b,category=setup
    for r in db_session.scalars(select(PropertyOwnership)):
        r.ownership_percentage=D('40')
    db_session.commit()
    data=values(setup);data['expense_date']='2026-09-01'
    response=client.post('/expenses/new',data=data,follow_redirects=False)
    assert response.status_code==303
    e=db_session.scalar(select(Expense))
    assert e.owner_id is None
    assert 'Requiere revisión de titularidad' in client.get(response.headers['location']).text
    ExpenseService().pay(db_session,e.id,effective_date=date(2026,9,10),amount='100',paid_by='manager',request_key=str(uuid4()))
    assert OwnerSettlementService().preview(db_session,a.id,date(2026,9,1),date(2026,10,1),[prop.id])['errors']
    assert db_session.scalar(select(func.count()).select_from(OwnerSettlementLine))==0
    del data['property_id']
    assert client.post('/expenses/new',data=data).status_code==200
    assert db_session.scalar(select(func.count()).select_from(Expense))==1


def test_ownership_information_and_explicit_owner_gate(db_session,setup,client):
    prop,a,b,category=setup
    info=client.get(f'/expenses/ownership?property_id={prop.id}&expense_date=2026-09-01').json()
    assert {o['id'] for o in info['owners']}=={a.id,b.id} and not info['warning']
    data=values(setup);data['expense_date']='2026-09-01';data['owner_id']=a.id
    client.post('/expenses/new',data=data)
    assert db_session.scalar(select(Expense)).owner_id is None
    data['imputation']='owner'
    client.post('/expenses/new',data=data)
    assert list(db_session.scalars(select(Expense).order_by(Expense.id)))[-1].owner_id==a.id


def test_single_owner_temporal_resolution_and_payment_detail(db_session,setup,client):
    prop,a,b,category=setup
    for row in db_session.scalars(select(PropertyOwnership)):
        row.active=False
    db_session.add(PropertyOwnership(property_id=prop.id,owner_id=a.id,ownership_percentage=D('100'),active=True,effective_from=date(2026,1,1),effective_until=date(2026,9,2)))
    db_session.add(PropertyOwnership(property_id=prop.id,owner_id=b.id,ownership_percentage=D('100'),active=True,effective_from=date(2026,9,2)))
    db_session.commit()
    e=ExpenseService().create(db_session,**values(setup))
    assert e.owner_id is None
    ExpenseService().pay(db_session,e.id,effective_date=date(2026,9,10),amount='100',paid_by='manager',method='bank_transfer',reference='Referencia sintética',request_key=str(uuid4()))
    view=OwnerSettlementService().preview(db_session,a.id,date(2026,9,1),date(2026,10,1),[prop.id])
    assert not view['errors'] and D(view['totals']['expenses'])==100
    other=OwnerSettlementService().preview(db_session,b.id,date(2026,9,1),date(2026,10,1),[prop.id])
    assert D(other['totals']['expenses'])==0
    html=client.get(f'/expenses/{e.id}').text
    assert 'Transferencia' in html and 'Referencia sintética' in html
