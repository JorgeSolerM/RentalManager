import pytest
from sqlalchemy import select,func
from tests.unit.test_owner_payout_corrections import paid,sample,args
from tests.integration.api.test_payment_correction_http import live_http,fields
from backend.models.owner_payout_correction import OwnerPayoutCorrectionOperation as Operation
from backend.services.owner_payout_balance_service import OwnerPayoutBalanceService

@pytest.mark.parametrize('kind',['void','replace'])
def test_full_real_http(live_http,db_session,paid,kind):
    s,p,a=paid;url=f'/settlements/{s.id}/payouts/{p.id}/review'
    assert live_http.get(url+'?kind='+kind).status_code==200
    values=args(kind);flag='no_transfer' if kind=='void' else 'same_transfer';values[flag]='yes'
    page=live_http.post(url+'/preview',data=values);assert page.status_code==200,page.text
    data=fields(page).hidden
    if kind=='void':assert 'amount' not in data
    assert live_http.post(url+'/confirm',data=data).status_code==409
    assert live_http.post(url+'/confirm',data=data|{'confirmed':'yes'}).status_code==409
    data.update(confirmed='yes',**{flag:'yes'})
    for _ in range(2):assert live_http.post(url+'/confirm',data=data).status_code==303
    history=live_http.get(url);assert history.status_code==200 and 'Rectificación sintética' in history.text
    page=live_http.get(f'/settlements/{s.id}');assert page.status_code==200
    assert ('Anulado' if kind=='void' else 'Sustituido') in page.text
    assert db_session.scalar(select(func.count()).select_from(Operation))==1
    assert OwnerPayoutBalanceService().summary(db_session,s)['paid']==(0 if kind=='void' else 150)

@pytest.mark.parametrize('kind',['void','replace'])
@pytest.mark.parametrize('action',['preview','confirm'])
def test_missing_fields(client,paid,kind,action):
    s,p,a=paid;url=f'/settlements/{s.id}/payouts/{p.id}/review/{action}'
    assert client.post(url,data={'kind':kind}).status_code==409


def test_wrong_destination_and_bad_requests(client,paid):
    s,p,a=paid;url=f'/settlements/{s.id}/payouts/{p.id}/review'
    for forbidden in ('owner_id','settlement_id','bank_account_id'):
        assert client.post(url+'/preview',data={'kind':'void','reason':'Error','no_transfer':'yes',forbidden:'999'}).status_code==409
    assert client.get('/settlements/999999/payouts/'+str(p.id)+'/review').status_code==404
    assert client.post(url+'/preview',data={}).status_code==400
    assert client.post(url+'/wrong',data={'kind':'void'}).status_code==409


def test_public_not_exposed():
    from fastapi.testclient import TestClient
    from backend.public.app_factory import create_public_app
    with TestClient(create_public_app()) as c:
        assert c.get('/settlements/1/payouts/1/review').status_code in (403,404)
        assert c.post('/settlements/1/payouts/1/review/confirm',data={'confirmed':'yes'}).status_code in (403,404,405)
