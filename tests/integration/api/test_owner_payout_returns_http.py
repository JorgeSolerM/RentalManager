import pytest
from sqlalchemy import select,func
from backend.models.owner_payout_return import OwnerPayoutReturn
from tests.unit.test_owner_payout_returns import paid,sample,values,returns,balances,register
from tests.integration.api.test_payment_correction_http import live_http,fields


def test_real_http_complete_flow(live_http,db_session,paid):
    s,p,a=paid;url=f'/settlements/{s.id}/payouts/{p.id}/returns'
    page=live_http.get(url);assert page.status_code==200 and 'no-store' in page.headers['cache-control']
    data=values();data['received']='yes'
    page=live_http.post(url+'/preview',data=data);assert page.status_code==200
    assert db_session.scalar(select(func.count()).select_from(OwnerPayoutReturn))==0
    data=fields(page).hidden
    assert live_http.post(url+'/confirm',data=data).status_code==409
    data.update(received='yes',confirmed='yes')
    assert live_http.post(url+'/confirm',data=data).status_code==303
    assert live_http.post(url+'/confirm',data=data).status_code==303
    assert db_session.scalar(select(func.count()).select_from(OwnerPayoutReturn))==1
    assert balances.summary(db_session,s)['paid']==60
    assert '40.00' in live_http.get(url+'#history').text
    assert a.iban not in live_http.get(url).text
    assert 'Devoluciones recibidas' in live_http.get(f'/settlements/{s.id}').text

@pytest.mark.parametrize('field',['amount','effective_date','bank_reference','reason','receiving_iban','received'])
@pytest.mark.parametrize('action',['preview','confirm'])
def test_missing_fields_not_500(client,paid,field,action):
    s,p,a=paid;data=values();data['received']='yes';del data[field]
    assert client.post(f'/settlements/{s.id}/payouts/{p.id}/returns/{action}',data=data).status_code==409


def test_blocked_and_target_tampering(client,db_session,paid):
    s,p,a=paid;url=f'/settlements/{s.id}/payouts/{p.id}/returns';data=values();data['received']='yes'
    assert client.post(url+'/preview',data=data|{'owner_id':'999'}).status_code==409
    register(db_session,s,p,amount='100')
    assert client.post(url+'/preview',data=data).status_code==409
    assert 'devuelto íntegramente' in client.get(url).text


def test_public_app_never_exposes_return_routes():
    from fastapi.testclient import TestClient
    from backend.public.app_factory import create_public_app
    with TestClient(create_public_app()) as public:
        for path in ['/settlements/1/payouts/1/returns','/settlements/1/payouts/1/returns/confirm']:
            assert public.get(path).status_code==404
            assert public.post(path,data={'received':'yes'}).status_code in (404,405)
