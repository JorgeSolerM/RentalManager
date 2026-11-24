from html.parser import HTMLParser
from threading import Thread
import socket,time
import httpx,pytest,uvicorn
from sqlalchemy import select,func
from backend.models.payment import Payment
from backend.models.payment_correction_operation import PaymentCorrectionOperation
from backend.models.owner_settlement import PaymentCustody
from tests.integration.api.test_payment_correction import sample,original_sample,settlement_sample,service

class FormInputs(HTMLParser):
    def __init__(self):super().__init__();self.hidden={};self.names=set()
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in ('input','textarea') and attrs.get('name'):self.names.add(attrs['name'])
        if tag=='input' and attrs.get('type')=='hidden':self.hidden[attrs['name']]=attrs.get('value','')
def fields(response):
    parsed=FormInputs();parsed.feed(response.text);return parsed

@pytest.fixture
def live_http(db_session):
    from backend.app_factory import create_app
    from backend.database.session import get_db
    app=create_app(initialize_database=False)
    def isolated():yield db_session
    app.dependency_overrides[get_db]=isolated
    sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='critical',access_log=False))
    thread=Thread(target=server.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    try:
        limit=time.monotonic()+15
        while not server.started:
            assert thread.is_alive() and time.monotonic()<limit
            time.sleep(.02)
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=15) as client:
            client.get('/')
            def browser_csrf(request):
                if request.method not in {'GET','HEAD','OPTIONS'}:
                    request.headers['X-RM-CSRF']=client.cookies['rm_admin_csrf']
                    request.headers['Origin']=f'http://127.0.0.1:{port}'
            client.event_hooks['request'].append(browser_csrf)
            yield client
    finally:
        server.should_exit=True;thread.join(15);sock.close()
        assert not thread.is_alive()

def test_real_http_void_complete_without_amount(live_http,db_session,sample):
    b,p,c=sample;url=f'/bookings/{b.id}/finance/payments/{p.id}/correction'
    original=(p.amount,p.effective_date,p.method,p.notes)
    allocations=[(a.id,a.amount) for a in service.assignments.allocations(db_session,p.id)]
    page=live_http.get(url+'?kind=void');assert page.status_code==200
    form=fields(page);assert 'amount' not in form.names
    payload=form.hidden|{'reason':'Cobro registrado por error'}
    page=live_http.post(url+'/preview',data=payload);assert page.status_code==200
    assert 'Vista previa del impacto' in page.text
    assert p.lifecycle=='posted' and not service.history(db_session,b.id)
    confirm=fields(page);assert 'amount' not in confirm.names
    payload=confirm.hidden
    assert live_http.post(url+'/confirm',data=payload).status_code==409
    payload['confirmed']='yes'
    assert live_http.post(url+'/confirm',data=payload).status_code==303
    assert live_http.post(url+'/confirm',data=payload).status_code==303
    db_session.expire_all()
    assert p.lifecycle=='void' and p.voided_at is not None
    assert original==(p.amount,p.effective_date,p.method,p.notes)
    assert db_session.scalar(select(func.count()).select_from(Payment))==1
    audit=service.history(db_session,b.id);assert len(audit)==1
    assert audit[0].reason=='Cobro registrado por error' and audit[0].before_amount==600
    assert audit[0].after_amount==0 and audit[0].replacement_payment_id is None
    assert allocations==[(a.id,a.amount) for a in service.assignments.allocations(db_session,p.id)]
    assert service.finance.booking_summary(db_session,b.id).received_total==0
    assert all(service.finance.charge_balance(db_session,x.id).outstanding_amount==400 for x in c)
    assert 'Cobro registrado por error' in live_http.get(f'/bookings/{b.id}/finance').text

@pytest.mark.parametrize('data',[
 {},{'kind':'void'},{'kind':'void','reason':''},
 {'kind':'replace','reason':'Error'}, {'kind':'replace','amount':'800'},
 {'kind':'replace','amount':'bad','reason':'Error'},
 {'kind':'void','reason':'Error','distribution_present':'yes','allocation_bad':'1'},
])
@pytest.mark.parametrize('action',['preview','confirm'])
def test_missing_or_invalid_fields_never_500(client,db_session,sample,data,action):
    b,p,c=sample
    response=client.post(f'/bookings/{b.id}/finance/payments/{p.id}/correction/{action}',data=data)
    assert response.status_code==409
    assert p.lifecycle=='posted' and not service.history(db_session,b.id)

@pytest.mark.parametrize('action',['preview','confirm'])
def test_missing_payment_404_without_amount(client,sample,action):
    b,p,c=sample
    response=client.post(f'/bookings/{b.id}/finance/payments/2147483647/correction/{action}',data={'kind':'void','reason':'Error','confirmed':'yes'})
    assert response.status_code in (404,409)
    if action=='preview':assert response.status_code==404

@pytest.mark.parametrize('blocker',['custody','refund','sepa'])
def test_http_void_blockers(client,db_session,sample,blocker):
    b,p,c=sample
    if blocker=='custody':db_session.delete(db_session.scalar(select(PaymentCustody).where(PaymentCustody.payment_id==p.id)))
    elif blocker=='sepa':p.method='sepa_direct_debit'
    else:db_session.add(Payment(booking_id=b.id,amount=10,effective_date=p.effective_date,lifecycle='posted',posted_at=p.posted_at,direction='refund',method='cash',corrects_payment_id=p.id))
    db_session.commit()
    url=f'/bookings/{b.id}/finance/payments/{p.id}/correction'
    for action in ['preview','confirm']:
        data={'kind':'void','reason':'Error','confirmed':'yes','request_key':'b8c1f620-9123-4567-8a12-123456789abc','expected':'stale'}
        assert client.post(url+'/'+action,data=data).status_code==409
    assert p.lifecycle=='posted' and not service.history(db_session,b.id)

def test_http_closed_settlement(client,db_session,settlement_sample):
    from tests.unit.test_owner_settlement_service import draft,service as settlements
    item=draft(db_session,settlement_sample);settlements.close(db_session,item.id,item.fingerprint)
    p=settlement_sample['payment'];url=f'/bookings/{p.booking_id}/finance/payments/{p.id}/correction'
    page=client.post(url+'/preview',data={'kind':'void','reason':'Error'})
    assert page.status_code==409 and 'liquidación cerrada' in page.text
    assert p.lifecycle=='posted'
