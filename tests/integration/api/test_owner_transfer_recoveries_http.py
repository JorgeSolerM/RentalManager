import pytest
from sqlalchemy import select,func
from backend.models.owner_transfer_recovery import OwnerTransferRecovery as Recovery
from backend.models.owner_settlement import OwnerPayout
from tests.unit.test_owner_transfer_recoveries import sample,paid,register,extra,incidents,balances,recoveries,inputs,payinputs,bank_return
from tests.integration.api.test_payment_correction_http import live_http,fields


def test_full_http_recovery_and_correct_payout(live_http,db_session,paid):
    s,p,a=paid;i=register(db_session,s,p);url=f'/transfer-incidents/{i.id}/recoveries';data=inputs(a);data['received']='yes'
    assert live_http.get(url).status_code==200
    response=live_http.post(url+'/preview',data=data);assert response.status_code==200,response.text
    assert db_session.scalar(select(func.count()).select_from(Recovery))==0
    hidden=fields(response).hidden
    assert live_http.post(url+'/confirm',data=hidden).status_code==409
    assert live_http.post(url+'/confirm',data=hidden|dict(confirmed='yes')).status_code==409
    for _ in range(2):assert live_http.post(url+'/confirm',data=hidden|dict(confirmed='yes',received='yes')).status_code==303
    response=live_http.get(url);assert response.status_code==200 and a.iban not in response.text and 'Registrar nuevo pago correcto' in response.text
    url=f'/settlements/{s.id}/payout';data=payinputs(a);data['paid']='yes'
    assert live_http.get(url+'/review').status_code==200
    response=live_http.post(url+'/preview',data=data);assert response.status_code==200,response.text
    hidden=fields(response).hidden
    assert live_http.post(url+'/confirm',data=hidden).status_code==409
    for _ in range(2):assert live_http.post(url+'/confirm',data=hidden|dict(confirmed='yes',paid='yes')).status_code==303
    assert balances.summary(db_session,s)['paid']==40 and db_session.scalar(select(func.count()).select_from(OwnerPayout))==2


@pytest.mark.parametrize('field',['amount','effective_date','receiving_iban','bank_reference','reason','evidence','received'])
@pytest.mark.parametrize('action',['preview','confirm'])
def test_absent_recovery_fields(client,db_session,paid,field,action):
    s,p,a=paid;i=register(db_session,s,p);v=inputs(a);v['received']='yes';del v[field]
    assert client.post(f'/transfer-incidents/{i.id}/recoveries/{action}',data=v).status_code==409
    assert db_session.scalar(select(func.count()).select_from(Recovery))==0


@pytest.mark.parametrize('field',['amount','effective_date','bank_account_id','reason','paid'])
@pytest.mark.parametrize('action',['preview','confirm'])
def test_absent_payout_fields(client,paid,field,action):
    s,p,a=paid;v=payinputs(a);v['paid']='yes';del v[field]
    assert client.post(f'/settlements/{s.id}/payout/{action}',data=v).status_code==409


def test_http_pending_attribution_and_link(client,db_session,paid):
    s,p,a=paid;ret=bank_return(db_session,s,p,amount='10');i=register(db_session,s,p,amount='90')
    base=f'/transfer-incidents/{i.id}/recoveries/link';v=dict(return_id=str(ret.id),reason='Vínculo documental')
    response=client.post(base+'/preview',data=v);assert response.status_code==200,response.text
    hidden=fields(response).hidden;before=balances.summary(db_session,s)['available']
    assert client.post(base+'/confirm',data=hidden).status_code==409
    assert client.post(base+'/confirm',data=hidden|dict(confirmed='yes'),follow_redirects=False).status_code==303
    assert balances.summary(db_session,s)['available']==before
    j=register(db_session,s,p,**extra(s,p,allocations={}))
    v=inputs(a,amount='20');v['received']='yes';base=f'/transfer-incidents/{j.id}/recoveries'
    response=client.post(base+'/preview',data=v);assert response.status_code==200,response.text
    assert client.post(base+'/confirm',data=fields(response).hidden|dict(confirmed='yes',received='yes'),follow_redirects=False).status_code==303
    r=db_session.scalar(select(Recovery));base=f'/transfer-recoveries/{r.id}/attribute'
    assert client.get(base).status_code==200
    assert client.post(base+'/preview',data=dict(reason='No source funds')).status_code==409
    v=incidents.attribution_preview(db_session,j.id,allocations={str(s.owner_id):'80'},reason='Synthetic source')
    from uuid import uuid4
    incidents.attribute(db_session,j.id,allocations={str(s.owner_id):'80'},reason='Synthetic source',request_key=str(uuid4()),expected=v['fingerprint'],confirmed=True)
    response=client.post(base+'/preview',data=dict(reason='Known recovered funds'));assert response.status_code==200,response.text
    hidden=fields(response).hidden
    assert client.post(base+'/confirm',data=hidden).status_code==409
    for _ in range(2):assert client.post(base+'/confirm',data=hidden|dict(confirmed='yes'),follow_redirects=False).status_code==303
    assert not balances.summary(db_session,s)['payout_blockers']


def test_recovery_endpoints_not_public():
    from fastapi.testclient import TestClient
    from backend.public.app_factory import create_public_app
    with TestClient(create_public_app()) as c:
        assert c.get('/transfer-incidents/1/recoveries').status_code==404
        assert c.post('/transfer-incidents/1/recoveries/confirm').status_code==404
        assert c.get('/settlements/1/payout/review').status_code==404



def test_new_registration_and_existing_corrections_coexist(client,paid):
    s,p,a=paid
    assert client.get(f'/settlements/{s.id}/payout/review').status_code==200
    assert client.get(f'/settlements/{s.id}/payouts/{p.id}/review').status_code==200
    assert client.get(f'/settlements/{s.id}/payouts/{p.id}/returns').status_code==200
