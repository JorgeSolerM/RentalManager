import pytest
from sqlalchemy import select,func
from backend.models.owner_loss_compensation import OwnerLossCompensationApplication as Application
from tests.unit.test_owner_loss_compensations import sample,paid,register,owner_loss,authorization_values,application_values,setup,balances
from tests.integration.api.test_payment_correction_http import live_http,fields

def test_real_http_authorize_apply_idempotent(live_http,db_session,paid):
    s,p,bank=paid;i=register(db_session,s,p);loss=owner_loss(db_session,s,i);url=f'/transfer-incidents/{i.id}/compensations'
    assert live_http.get(url).status_code==200
    v=authorization_values(s,loss);v['authorized']='yes'
    response=live_http.post(url+'/preview',data=v);assert response.status_code==200,response.text
    data=fields(response).hidden
    assert live_http.post(url+'/confirm',data=data).status_code==409
    for _ in range(2):assert live_http.post(url+'/confirm',data=data|dict(authorized='yes',confirmed='yes')).status_code==303
    from backend.models.owner_loss_compensation import OwnerLossCompensationAuthorization
    a=db_session.scalar(select(OwnerLossCompensationAuthorization));v=application_values(s,a)
    response=live_http.post(url+'/preview',data=v);assert response.status_code==200,response.text
    data=fields(response).hidden
    for _ in range(2):assert live_http.post(url+'/confirm',data=data|dict(confirmed='yes')).status_code==303
    assert db_session.scalar(select(func.count()).select_from(Application))==1
    assert balances.summary(db_session,s)['compensated']==40
    for path in (url,f'/settlements/{s.id}',f'/settlements/{s.id}/compensations'):
        response=live_http.get(path);assert response.status_code==200,response.text
        assert bank.iban not in response.text

@pytest.mark.parametrize('mode',['authorize','apply'])
@pytest.mark.parametrize('field',['mode','amount','reason','evidence','identity'])
@pytest.mark.parametrize('action',['preview','confirm'])
def test_missing_fields_never_500(client,db_session,paid,mode,field,action):
    s,p,bank=paid;i,loss,a=setup(db_session,s,p);v=authorization_values(s,loss) if mode=='authorize' else application_values(s,a)
    v.pop(('loss_id' if mode=='authorize' else 'authorization_id') if field=='identity' else field)
    assert client.post(f'/transfer-incidents/{i.id}/compensations/{action}',data=v).status_code==409
    assert db_session.scalar(select(func.count()).select_from(Application))==0

def test_public_exclusion_and_404(client):
    assert client.get('/transfer-incidents/2147483647/compensations').status_code==404
    from backend.public.app_factory import create_public_app
    assert not any('compensations' in getattr(r,'path','') for r in create_public_app().routes)
