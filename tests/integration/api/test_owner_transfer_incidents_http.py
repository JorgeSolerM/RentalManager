import pytest
from sqlalchemy import select,func
from backend.models.owner_transfer_incident import OwnerTransferIncident as Incident,OwnerTransferOutflow as Outflow
from tests.unit.test_owner_transfer_incidents import sample,paid,values,incidents,balances
from tests.integration.api.test_payment_correction_http import live_http,fields

def test_complete_http_incident(live_http,db_session,paid):
    s,p,a=paid;url=f'/settlements/{s.id}/transfer-incidents';data=values(s,p);data['executed']='yes'
    assert live_http.get(url+'/new').status_code==200
    response=live_http.post(url+'/preview',data=data);assert response.status_code==200,response.text
    assert db_session.scalar(select(func.count()).select_from(Incident))==0
    hidden=fields(response).hidden
    assert live_http.post(url+'/confirm',data=hidden).status_code==409
    for _ in range(2):assert live_http.post(url+'/confirm',data=hidden|dict(executed='yes',confirmed='yes')).status_code==303
    incident=db_session.scalar(select(Incident));response=live_http.get(f'/transfer-incidents/{incident.id}')
    assert response.status_code==200 and 'Historial inmutable' in response.text and a.iban not in response.text
    assert balances.summary(db_session,s)['paid']==0 and balances.summary(db_session,s)['available']==100
    assert db_session.scalar(select(func.count()).select_from(Outflow))==0

@pytest.mark.parametrize('field',['source_kind','kind','amount','reason','evidence','executed','payout_id'])
@pytest.mark.parametrize('action',['preview','confirm'])
def test_missing_fields(client,paid,field,action):
    s,p,a=paid;data=values(s,p);data['executed']='yes';del data[field]
    assert client.post(f'/settlements/{s.id}/transfer-incidents/{action}',data=data).status_code==409


def test_not_public():
    from fastapi.testclient import TestClient
    from backend.public.app_factory import create_public_app
    with TestClient(create_public_app()) as c:
        assert c.get('/transfer-incidents/1').status_code==404
        assert c.post('/settlements/1/transfer-incidents/confirm').status_code==404


def test_preview_render(client,paid):
    s,p,a=paid;data=values(s,p);data['executed']='yes'
    response=client.post(f'/settlements/{s.id}/transfer-incidents/preview',data=data)
    assert response.status_code==200


def test_http_extra_and_attribution(client,db_session,paid):
    s,p,a=paid;url=f'/settlements/{s.id}/transfer-incidents'
    data=dict(source_kind='extraordinary',kind='unknown_recipient',amount='300',effective_date='2026-09-23',reference='SYNTHETIC-EXTRA',bank_transaction_id='HTTP-OUT',reason='Salida real sintética',evidence='Extracto sintético',executed='yes')
    response=client.post(url+'/preview',data=data);assert response.status_code==200
    hidden=fields(response).hidden
    response=client.post(url+'/confirm',data=hidden|dict(confirmed='yes',executed='yes'),follow_redirects=False);assert response.status_code==303
    incident=db_session.scalar(select(Incident));assert balances.summary(db_session,s)['payout_blockers']
    url=f'/transfer-incidents/{incident.id}/attribute'
    assert client.post(url+'/preview',data={}).status_code==409
    response=client.post(url+'/preview',data={f'fund_{s.owner_id}':'300','reason':'Atribución acreditada'});assert response.status_code==200
    hidden=fields(response).hidden
    assert client.post(url+'/confirm',data=hidden).status_code==409
    for _ in range(2):assert client.post(url+'/confirm',data=hidden|dict(confirmed='yes'),follow_redirects=False).status_code==303
    b=balances.summary(db_session,s);assert b['deficit']==200 and not b['payout_blockers'] and b['available']==0
    assert client.get(f'/transfer-incidents/{incident.id}').status_code==200

@pytest.mark.parametrize('field',['effective_date','reference','reason','evidence','amount','executed'])
def test_extra_missing_fields(client,paid,field):
    s,p,a=paid;data=dict(source_kind='extraordinary',kind='unknown_recipient',amount='30',effective_date='2026-09-23',reference='HTTP-EXTRA',reason='Synthetic',evidence='Synthetic',executed='yes');del data[field]
    assert client.post(f'/settlements/{s.id}/transfer-incidents/preview',data=data).status_code==409
