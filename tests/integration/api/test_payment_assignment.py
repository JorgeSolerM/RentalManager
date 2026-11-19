from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func, event
from sqlalchemy.orm import Session
from backend.models.payment import Payment
from backend.models.payment_allocation import PaymentAllocation
from backend.models.payment_allocation_operation import PaymentAllocationOperation
from backend.models.booking_charge import BookingCharge
from backend.services.payment_assignment_service import PaymentAssignmentService
from tests.integration.api.test_booking_finance_routes import make_finance_booking
from tests.unit.test_owner_settlement_service import sample as settlement_sample

service=PaymentAssignmentService()

@pytest.fixture
def sample(db_session):
    booking=make_finance_booking(db_session)
    payment=Payment(booking_id=booking.id,amount=Decimal('600'),effective_date=date(2026,10,1),
        lifecycle='posted',posted_at=datetime(2026,10,1),direction='receipt',method='cash')
    charges=[BookingCharge(booking_id=booking.id,type='rent',concept=f'Renta sintética {month}',
        amount=Decimal('400'),due_date=date(2026,month,1),lifecycle='posted',posted_at=datetime(2026,9,1)) for month in (9,10)]
    db_session.add_all([payment,*charges]);db_session.commit()
    return booking,payment,charges

def assign(db,sample,pairs=None,**kwargs):
    b,p,charges=sample
    pairs=pairs or [(charges[0].id,'100')]
    review=service.preview(db,b.id,p.id,pairs)
    return service.confirm(db,b.id,p.id,pairs,request_key=kwargs.pop('request_key',str(uuid4())),
        expected=review['fingerprint'],confirmed=True,**kwargs)

def test_unassigned_partial_multiple_history(db_session,sample):
    b,p,charges=sample
    original=(p.amount,p.effective_date,p.method,b.check_in,b.check_out)
    assert service.unassigned(db_session,b.id)[0]['available']==600
    operation=assign(db_session,sample,[(charges[0].id,'200'),(charges[1].id,'100')])
    assert operation.amount==300 and len(operation.changes)==2
    assert service.available(db_session,p)==300
    assert service.finance.charge_balance(db_session,charges[0].id).outstanding_amount==200
    assert service.finance.charge_balance(db_session,charges[1].id).outstanding_amount==300
    assert db_session.scalar(select(func.count()).select_from(Payment))==1
    assert original==(p.amount,p.effective_date,p.method,b.check_in,b.check_out)

def test_partial_existing_pair_and_full_assignment(client,db_session,sample):
    b,p,c=sample
    first=assign(db_session,sample)
    aid=first.changes[0]['allocation_id']
    second=assign(db_session,sample,[(c[0].id,'300'),(c[1].id,'200')])
    assert second.changes[0]==dict(allocation_id=aid,charge_id=c[0].id,before='100.00',added='300.00',after='400.00')
    assert first.changes[0]['after']=='100.00'
    assert service.available(db_session,p)==0 and service.unassigned(db_session,b.id)==[]
    assert 'Ver asignaciones e historial' in client.get(f'/bookings/{b.id}/finance').text
    assert 'Historial de asignaciones posteriores' in client.get(f'/bookings/{b.id}/finance/payments/{p.id}/assign').text
    assert db_session.scalar(select(func.count()).select_from(PaymentAllocation))==2

@pytest.mark.parametrize('amounts',[['401','0'],['400','300'],['-1','0'],['NaN','0']])
def test_invalid_amounts_atomic(db_session,sample,amounts):
    b,p,c=sample
    pairs=[(charge.id,value) for charge,value in zip(c,amounts) if value!='0']
    with pytest.raises(ValueError):assign(db_session,sample,pairs)
    assert service.available(db_session,p)==600
    assert db_session.scalar(select(func.count()).select_from(PaymentAllocationOperation))==0

def test_cross_booking_currency_and_duplicate_charge(db_session,sample):
    b,p,c=sample
    other=make_finance_booking(db_session)
    with pytest.raises(ValueError):service.preview(db_session,other.id,p.id,[(c[0].id,'100')])
    c[1].booking_id=other.id;db_session.commit()
    with pytest.raises(ValueError):assign(db_session,sample,[(c[1].id,'100')])
    with pytest.raises(ValueError):assign(db_session,sample,[(c[0].id,'100'),(c[0].id,'100')])
    c[0].currency='USD';db_session.commit()
    with pytest.raises(ValueError):assign(db_session,sample)

def test_replay_and_key_reuse(db_session,sample):
    b,p,c=sample;pairs=[(c[0].id,'100')];key=str(uuid4())
    view=service.preview(db_session,b.id,p.id,pairs)
    one=service.confirm(db_session,b.id,p.id,pairs,request_key=key,expected=view['fingerprint'],confirmed=True)
    two=service.confirm(db_session,b.id,p.id,pairs,request_key=key,expected=view['fingerprint'],confirmed=True)
    assert one.request_key==two.request_key and service.available(db_session,p)==500
    with pytest.raises(ValueError):service.confirm(db_session,b.id,p.id,[(c[0].id,'101')],request_key=key,expected='',confirmed=True)

def test_stale_and_explicit_confirmation(db_session,sample):
    b,p,c=sample;pairs=[(c[0].id,'100')];view=service.preview(db_session,b.id,p.id,pairs)
    with pytest.raises(ValueError):service.confirm(db_session,b.id,p.id,pairs,request_key=str(uuid4()),expected=view['fingerprint'])
    assign(db_session,sample,[(c[1].id,'100')])
    with pytest.raises(ValueError,match='cambiado'):
        service.confirm(db_session,b.id,p.id,pairs,request_key=str(uuid4()),expected=view['fingerprint'],confirmed=True)

def test_concurrent_duplicate_and_different_request(db_session,sample):
    b,p,c=sample;bid=b.id;pid=p.id;pairs=[(c[0].id,'100')];key=str(uuid4())
    view=service.preview(db_session,bid,pid,pairs)
    def run(request_key):
        with Session(db_session.bind) as db:
            try:return service.confirm(db,bid,pid,pairs,request_key=request_key,expected=view['fingerprint'],confirmed=True).request_key
            except ValueError:return 'stale'
    with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(run,[key,key]))
    assert result==[key,key]
    assert run(str(uuid4()))=='stale'
    db_session.expire_all()
    assert service.available(db_session,p)==500

def test_closed_settlement_protects_payment_and_charge(db_session,settlement_sample):
    from tests.unit.test_owner_settlement_service import draft,service as settlements
    item=draft(db_session,settlement_sample);settlements.close(db_session,item.id,item.fingerprint)
    before=json_snapshot(item.snapshot)
    p=settlement_sample['payment'];c=settlement_sample['charge']
    assert 'liquidación cerrada' in service.payment_blocker(db_session,p)
    assert 'liquidación cerrada' in service.charge_blocker(db_session,c)
    with pytest.raises(ValueError):service.preview(db_session,p.booking_id,p.id,[(c.id,'1')])
    assert before==json_snapshot(item.snapshot)

def json_snapshot(value):
    import json
    return json.dumps(value,sort_keys=True)

def test_refund_void_draft_not_available(db_session,sample):
    b,p,c=sample
    refund=Payment(booking_id=b.id,amount=10,effective_date=date(2026,10,2),direction='refund',method='cash',
        lifecycle='posted',posted_at=datetime(2026,10,2),corrects_payment_id=p.id)
    db_session.add(refund);db_session.commit()
    with pytest.raises(ValueError,match='devolución'):assign(db_session,sample)
    for lifecycle in ['draft','void']:
        p.lifecycle=lifecycle;p.voided_at=datetime(2026,10,2);db_session.commit()
        with pytest.raises(ValueError):assign(db_session,sample)
        assert service.unassigned(db_session,b.id)==[]

def test_failure_rolls_back_allocations(db_session,sample):
    def fail(*args):raise RuntimeError('simulated audit write failure')
    event.listen(PaymentAllocationOperation,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError):assign(db_session,sample)
    finally:event.remove(PaymentAllocationOperation,'before_insert',fail)
    assert db_session.scalar(select(func.count()).select_from(PaymentAllocation))==0
    assert service.available(db_session,sample[1])==600

def test_admin_preview_confirm_history_and_errors(client,db_session,sample):
    b,p,c=sample;base=f'/bookings/{b.id}/finance/payments/{p.id}/assign'
    assert 'Asignar cobro' in client.get(f'/bookings/{b.id}/finance').text
    page=client.get(base);assert page.status_code==200 and '600.00' in page.text
    page=client.post(base+'/preview',data={f'allocation_{c[0].id}':'100'})
    assert page.status_code==200 and 'Revisar asignación' in page.text
    assert db_session.scalar(select(func.count()).select_from(PaymentAllocation))==0
    view=service.preview(db_session,b.id,p.id,[(c[0].id,'100')])
    data={f'allocation_{c[0].id}':'100','request_key':str(uuid4()),'expected':view['fingerprint'],'confirmed':'yes'}
    response=client.post(base+'/confirm',data=data,follow_redirects=False);assert response.status_code==303
    html=client.get(base).text;assert '500.00' in html and 'antes 0.00' in html
    error=client.post(base+'/preview',data={f'allocation_{c[0].id}':'999'})
    assert error.status_code==409 and 'text/html' in error.headers['content-type'] and 'saldo disponible' in error.text


def test_public_routes_are_not_exposed():
    from fastapi.testclient import TestClient
    from backend.public.app_factory import create_public_app
    with TestClient(create_public_app()) as public:
        path='/bookings/1/finance/payments/1/assign'
        assert public.get(path).status_code in (403,404)
        assert public.post(path+'/confirm',data={'confirmed':'yes'}).status_code in (403,404,405)


def test_reserved_sepa_charge_blocks(db_session,scenario):
    from tests.integration.api.test_sepa_collections import create
    from backend.services.manual_payment_service import ManualPaymentService
    from tests.integration.api.test_sepa_collections import COLLECTION
    create(db_session,scenario)
    b=scenario[1];charge=scenario[4][0]
    p=Payment(booking_id=b.id,amount=100,effective_date=COLLECTION,direction='receipt',
        method='cash',lifecycle='posted',posted_at=datetime(2026,9,1))
    db_session.add(p);db_session.commit()
    assert 'remesa' in service.charge_blocker(db_session,charge)
    with pytest.raises(ValueError,match='remesa'):
        service.preview(db_session,b.id,p.id,[(charge.id,'100')])


from tests.integration.api.test_sepa_collections import scenario
