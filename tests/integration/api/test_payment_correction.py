from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func, event
from sqlalchemy.orm import Session
from backend.models.payment import Payment
from backend.models.payment_allocation import PaymentAllocation
from backend.models.payment_correction_operation import PaymentCorrectionOperation
from backend.models.owner_settlement import PaymentCustody
from backend.services.payment_correction_service import PaymentCorrectionService
from tests.integration.api.test_payment_assignment import sample as original_sample, assign, settlement_sample

service=PaymentCorrectionService()

@pytest.fixture
def sample(db_session,original_sample):
    b,p,c=original_sample
    db_session.add(PaymentCustody(payment_id=p.id,actor='manager',amount=p.amount));db_session.commit()
    assign(db_session,original_sample,[(c[0].id,'200'),(c[1].id,'100')])
    return b,p,c

def correct(db,sample,**kwargs):
    b,p,c=sample
    values=dict(kind='replace',amount='800',reason='Error de transcripción');values.update(kwargs)
    review=service.preview(db,b.id,p.id,**values)
    return service.confirm(db,b.id,p.id,**values,request_key=str(uuid4()),expected=review['fingerprint'],confirmed=True)

@pytest.mark.parametrize('amount,free',[('800',500),('500',200)])
def test_replace_preserves_history_and_custody(db_session,sample,amount,free):
    b,p,c=sample
    original=(p.effective_date,p.method,p.external_reference,p.notes)
    old_alloc=[(a.id,a.amount) for a in service.assignments.allocations(db_session,p.id)]
    op=correct(db_session,sample,amount=amount)
    new=db_session.get(Payment,op.replacement_payment_id)
    assert p.lifecycle=='void' and p.amount==600
    assert (new.effective_date,new.method,new.external_reference,new.notes)==original
    assert old_alloc==[(a.id,a.amount) for a in service.assignments.allocations(db_session,p.id)]
    assert new.corrects_payment_id==p.id
    assert service.assignments.available(db_session,new)==free
    assert service.finance.booking_summary(db_session,b.id).received_total==new.amount
    custody=db_session.scalar(select(PaymentCustody).where(PaymentCustody.payment_id==new.id))
    assert custody.actor=='manager' and custody.amount==new.amount
    assert len(service.history(db_session,b.id))==1

def test_void_reopens_charges_without_refund(db_session,sample):
    b,p,c=sample;op=correct(db_session,sample,kind='void')
    assert op.replacement_payment_id is None and p.lifecycle=='void'
    assert db_session.scalar(select(func.count()).select_from(Payment))==1
    assert service.finance.booking_summary(db_session,b.id).received_total==0
    assert all(service.finance.charge_balance(db_session,x.id).outstanding_amount==400 for x in c)
    assert len(service.assignments.allocations(db_session,p.id))==2

def test_manual_redistribution(db_session,sample):
    b,p,c=sample
    with pytest.raises(ValueError,match='distribución'):correct(db_session,sample,amount='250')
    op=correct(db_session,sample,amount='250',pairs=[(c[0].id,'150'),(c[1].id,'100')],redistributed=True)
    assert op.after_amount==250
    assert service.finance.charge_balance(db_session,c[0].id).outstanding_amount==250
    assert service.finance.charge_balance(db_session,c[1].id).outstanding_amount==300

@pytest.mark.parametrize('values',[{'reason':''},{'amount':'0'},{'amount':'NaN'},{'amount':'600'},{'amount':'-10'},{'amount':'250','redistributed':True,'pairs':[(99999,'250')]}])
def test_invalid_no_writes(db_session,sample,values):
    with pytest.raises(ValueError):correct(db_session,sample,**values)
    assert sample[1].lifecycle=='posted'
    assert db_session.scalar(select(func.count()).select_from(PaymentCorrectionOperation))==0

def test_duplicate_concurrent_stale(db_session,sample):
    b,p,c=sample;bid=b.id;pid=p.id
    values=dict(kind='replace',amount='800',reason='Importe erróneo')
    review=service.preview(db_session,bid,pid,**values);key=str(uuid4())
    def run(k):
        with Session(db_session.bind) as db:
            try:return service.confirm(db,bid,pid,**values,request_key=k,expected=review['fingerprint'],confirmed=True).request_key
            except ValueError:return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(run,[key,key]))==[key,key]
    assert run(str(uuid4()))=='blocked'
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(Payment))==2

def test_changed_preview_and_confirmation(db_session,sample):
    b,p,c=sample;values=dict(kind='replace',amount='800',reason='Error')
    review=service.preview(db_session,b.id,p.id,**values)
    with pytest.raises(ValueError):service.confirm(db_session,b.id,p.id,**values,request_key=str(uuid4()),expected=review['fingerprint'])
    assign(db_session,sample,[(c[1].id,'50')])
    with pytest.raises(ValueError,match='cambiado'):service.confirm(db_session,b.id,p.id,**values,request_key=str(uuid4()),expected=review['fingerprint'],confirmed=True)

def test_rollback_all_steps(db_session,sample):
    def fail(*args):raise RuntimeError('synthetic failure')
    event.listen(PaymentCorrectionOperation,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError):correct(db_session,sample)
    finally:event.remove(PaymentCorrectionOperation,'before_insert',fail)
    db_session.expire_all()
    assert sample[1].lifecycle=='posted'
    assert db_session.scalar(select(func.count()).select_from(Payment))==1
    assert db_session.scalar(select(func.count()).select_from(PaymentCustody))==1
    assert db_session.scalar(select(func.count()).select_from(PaymentAllocation))==2

def test_chain_and_later_assignment(db_session,sample):
    b,p,c=sample;one=correct(db_session,sample)
    new=db_session.get(Payment,one.replacement_payment_id)
    two=correct(db_session,(b,new,c),amount='700')
    latest=db_session.get(Payment,two.replacement_payment_id)
    assign(db_session,(b,latest,c),[(c[0].id,'50')])
    assert len(service.history(db_session,b.id))==2
    assert service.finance.booking_summary(db_session,b.id).received_total==700
    assert service.assignments.available(db_session,latest)==350
    with pytest.raises(ValueError):assign(db_session,sample)

def test_closed_settlement(db_session,settlement_sample):
    from tests.unit.test_owner_settlement_service import draft,service as settlements
    item=draft(db_session,settlement_sample);settlements.close(db_session,item.id,item.fingerprint)
    p=settlement_sample['payment']
    with pytest.raises(ValueError,match='liquidación cerrada'):service.preview(db_session,p.booking_id,p.id,kind='void',reason='Error')

@pytest.mark.parametrize('mode',['missing','mismatch','sepa','refund'])
def test_blockers(db_session,sample,mode):
    b,p,c=sample;custody=db_session.scalar(select(PaymentCustody).where(PaymentCustody.payment_id==p.id))
    if mode=='missing':db_session.delete(custody)
    elif mode=='mismatch':custody.amount=599
    elif mode=='sepa':p.method='sepa_direct_debit'
    else:db_session.add(Payment(booking_id=b.id,amount=10,effective_date=p.effective_date,lifecycle='posted',posted_at=p.posted_at,direction='refund',method='cash',corrects_payment_id=p.id))
    db_session.commit()
    with pytest.raises(ValueError):correct(db_session,sample)

def test_routes_preview_history_no_write(client,db_session,sample):
    b,p,c=sample;url=f'/bookings/{b.id}/finance/payments/{p.id}/correction'
    response=client.get(url);assert response.status_code==200 and 'Motivo obligatorio' in response.text
    assert client.post(url+'/preview',data={'kind':'replace','amount':'800','reason':'Error sintético'}).status_code==200
    assert p.lifecycle=='posted' and len(service.history(db_session,b.id))==0
    op=correct(db_session,sample)
    account=client.get(f'/bookings/{b.id}/finance')
    assert account.status_code==200 and 'Sustituido' in account.text and 'Asignaciones históricas sin efecto' in account.text
    assert 'Cobro sustituto' in client.get(f'/bookings/{b.id}/finance/payments/{p.id}/assign').text


def test_owner_custody(db_session,sample):
    from backend.models.owner import Owner
    b,p,c=sample;owner=Owner(legal_name='Propietario sintético');db_session.add(owner);db_session.flush()
    custody=db_session.scalar(select(PaymentCustody).where(PaymentCustody.payment_id==p.id))
    custody.actor='owner';custody.owner_id=owner.id;db_session.commit()
    op=correct(db_session,sample)
    new=db_session.scalar(select(PaymentCustody).where(PaymentCustody.payment_id==op.replacement_payment_id))
    assert new.actor=='owner' and new.owner_id==owner.id and new.amount==800

def test_full_and_unassigned(db_session,sample):
    b,p,c=sample
    assign(db_session,sample,[(c[0].id,'200'),(c[1].id,'100')])
    op=correct(db_session,sample,amount='500',pairs=[(c[0].id,'300'),(c[1].id,'200')],redistributed=True)
    new=db_session.get(Payment,op.replacement_payment_id)
    assert service.assignments.available(db_session,new)==0

def test_void_legacy_entry_requires_reason_and_audits(db_session,sample):
    b,p,c=sample
    assert not service.finance.void_payment(db_session,p.id).success
    assert service.finance.void_payment(db_session,p.id,notes='Error registrado').success
    assert len(service.history(db_session,b.id))==1


def test_unassigned_correction(db_session,original_sample):
    b,p,c=original_sample
    db_session.add(PaymentCustody(payment_id=p.id,actor='manager',amount=p.amount));db_session.commit()
    op=correct(db_session,original_sample,amount='500')
    new=db_session.get(Payment,op.replacement_payment_id)
    assert service.assignments.available(db_session,new)==500
    assert not service.assignments.allocations(db_session,new.id)

def test_invalid_distribution_and_cross_booking(db_session,sample):
    b,p,c=sample
    for pairs in [[(c[0].id,'200'),(c[1].id,'100')],[(c[0].id,'150'),(c[0].id,'100')]]:
        with pytest.raises(ValueError):correct(db_session,sample,amount='250',pairs=pairs,redistributed=True)
    from tests.integration.api.test_booking_finance_routes import make_finance_booking
    other=make_finance_booking(db_session)
    with pytest.raises(ValueError):service.preview(db_session,other.id,p.id,kind='void',reason='Error')

def test_public_correction_inaccessible():
    from fastapi.testclient import TestClient
    from backend.public.app_factory import create_public_app
    with TestClient(create_public_app()) as public:
        url='/bookings/1/finance/payments/1/correction'
        assert public.get(url).status_code in (403,404)
        assert public.post(url+'/confirm',data={'confirmed':'yes'}).status_code in (403,404,405)

from tests.integration.api.test_sepa_collections import scenario

def test_reserved_charge(db_session,scenario):
    from tests.integration.api.test_sepa_collections import create,COLLECTION
    from datetime import datetime
    create(db_session,scenario);b=scenario[1];c=scenario[4][0]
    p=Payment(booking_id=b.id,amount=100,effective_date=COLLECTION,direction='receipt',method='cash',lifecycle='posted',posted_at=datetime(2026,9,1))
    db_session.add(p);db_session.flush()
    db_session.add_all([PaymentCustody(payment_id=p.id,actor='manager',amount=100),PaymentAllocation(payment_id=p.id,charge_id=c.id,amount=100)]);db_session.commit()
    with pytest.raises(ValueError,match='remesa'):service.preview(db_session,b.id,p.id,kind='void',reason='Error')

def test_html_confirmation_and_title(client,db_session,sample):
    from html.parser import HTMLParser
    class Inputs(HTMLParser):
        def __init__(self):super().__init__();self.payload={}
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if tag=='input' and attrs.get('type')=='hidden':self.payload[attrs['name']]=attrs.get('value','')
    b,p,c=sample;url=f'/bookings/{b.id}/finance/payments/{p.id}/correction'
    response=client.post(url+'/preview',data={'kind':'replace','amount':'800','reason':'Error sintético'})
    parser=Inputs();parser.feed(response.text);payload=parser.payload;payload['confirmed']='yes'
    assert client.post(url+'/confirm',data=payload,follow_redirects=False).status_code==303
    assert client.post(url+'/confirm',data=payload,follow_redirects=False).status_code==303
    assert db_session.scalar(select(func.count()).select_from(PaymentCorrectionOperation))==1
    for path in [f'/bookings/{b.id}/finance',f'/bookings/{b.id}/finance/payments/{p.id}/assign']:
        html=client.get(path).text
        assert '<' not in html.split('<title>')[1].split('</title>')[0]
        assert 'Historial de correcciones' in html.split('<body')[1]
