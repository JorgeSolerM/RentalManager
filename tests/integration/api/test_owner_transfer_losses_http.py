import pytest
from sqlalchemy import select,func
from backend.models.owner_transfer_regularization import OwnerTransferRegularizationOperation as Operation
from tests.unit.test_owner_transfer_losses import sample,paid,register,losses,values,economic
from tests.integration.api.test_payment_correction_http import live_http,fields

def test_real_http_recognition_and_assignment(live_http,db_session,paid):
    s,p,a=paid;i=register(db_session,s,p);url=f'/transfer-incidents/{i.id}/regularizations';before=economic(db_session,s)
    assert live_http.get(url).status_code==200
    response=live_http.post(url+'/preview',data=values());assert response.status_code==200,response.text
    data=fields(response).hidden
    assert live_http.post(url+'/confirm',data=data).status_code==409
    for _ in range(2):assert live_http.post(url+'/confirm',data=data|dict(confirmed='yes')).status_code==303
    row=db_session.scalar(select(Operation));assert row.kind=='recognize'
    v=values(kind='responsibility',loss_id=str(row.id),responsible='owner',responsible_owner_id=str(s.owner_id),agreement='Acuerdo sintético firmado',authorized='yes')
    response=live_http.post(url+'/preview',data=v);assert response.status_code==200,response.text
    data=fields(response).hidden
    assert live_http.post(url+'/confirm',data=data|dict(confirmed='yes')).status_code==409
    for _ in range(2):assert live_http.post(url+'/confirm',data=data|dict(confirmed='yes',authorized='yes')).status_code==303
    assert economic(db_session,s)==before and db_session.scalar(select(func.count()).select_from(Operation))==2
    response=live_http.get(url);assert response.status_code==200 and a.iban not in response.text and 'Acuerdo sintético firmado' in response.text

@pytest.mark.parametrize('field',['amount','kind','responsible','reason','evidence','evidence_reference'])
@pytest.mark.parametrize('action',['preview','confirm'])
def test_missing_fields(client,db_session,paid,field,action):
    s,p,a=paid;i=register(db_session,s,p);v=values();v.pop(field)
    assert client.post(f'/transfer-incidents/{i.id}/regularizations/{action}',data=v).status_code==409
    assert db_session.scalar(select(func.count()).select_from(Operation))==0

def test_missing_id_and_public_exclusion(client):
    assert client.get('/transfer-incidents/2147483647/regularizations').status_code==404
    from backend.public.app_factory import create_public_app
    app=create_public_app()
    assert not any('regularizations' in getattr(r,'path','') for r in app.routes)
