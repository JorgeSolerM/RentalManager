from datetime import date
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import pytest
from sqlalchemy import select,func,event
from sqlalchemy.orm import Session
from backend.models.owner_payout_return import OwnerPayoutReturn
from backend.models.owner_settlement import OwnerPayout,OwnerSettlement
from backend.services.owner_payout_return_service import OwnerPayoutReturnService
from tests.unit.test_owner_payout_corrections import paid,sample,balances,corrections,args,apply,raw,draft,service

returns=OwnerPayoutReturnService()
def values(**changes):
    v=dict(amount='40',effective_date='2026-09-22',bank_reference='SYNTHETIC RETURN',reason='Abono bancario sintético recibido',receiving_iban='ES9121000418450200051332',received=True)
    v.update(changes);return v

def register(db,s,p,**changes):
    v=values(**changes);review=returns.preview(db,s.id,p.id,**v)
    return returns.confirm(db,s.id,p.id,**v,request_key=str(uuid4()),expected=review['fingerprint'],confirmed=True)

@pytest.mark.parametrize('amount',['40','100'])
def test_full_partial_immutable_balances(db_session,paid,amount):
    s,p,a=paid;before=raw(p);closed=raw(s)
    r=register(db_session,s,p,amount=amount);b=balances.summary(db_session,s)
    assert b['gross_paid']==100 and b['returned']==int(amount)
    assert b['paid']==100-int(amount) and b['remaining']==100+int(amount)
    assert b['available']==100+int(amount)
    assert raw(p)==before and raw(s)==closed and r.received
    assert db_session.scalar(select(func.count()).select_from(OwnerPayout))==1


def test_multiple_returns_and_limit(db_session,paid):
    s,p,a=paid
    register(db_session,s,p,amount='40');register(db_session,s,p,amount='30')
    assert returns.form(db_session,s.id,p.id)['maximum']==30
    with pytest.raises(ValueError):register(db_session,s,p,amount='31')
    register(db_session,s,p,amount='30',effective_date='2026-09-23')
    assert balances.summary(db_session,s)['paid']==0
    with pytest.raises(ValueError):register(db_session,s,p,amount='1')

@pytest.mark.parametrize('change',[{'amount':'101'},{'amount':'0'},{'amount':'-1'},{'amount':'NaN'},{'amount':None},{'received':False},{'reason':''},{'bank_reference':''},{'receiving_iban':'bad'},{'effective_date':'2099-01-01'},{'effective_date':'2026-09-19'}])
def test_validation(db_session,paid,change):
    s,p,a=paid
    with pytest.raises(ValueError):register(db_session,s,p,**change)
    assert balances.summary(db_session,s)['paid']==100


def test_duplicate_other_keys_reference_and_bank_id(db_session,paid):
    s,p,a=paid;register(db_session,s,p,bank_transaction_id=' BANK-1 ')
    with pytest.raises(ValueError):register(db_session,s,p,bank_transaction_id='bank-1',amount='10',effective_date='2026-09-23')
    with pytest.raises(ValueError):register(db_session,s,p,bank_reference='CHANGED')
    register(db_session,s,p,bank_transaction_id='BANK-2')
    assert balances.summary(db_session,s)['returned']==80


def test_fallback_duplicate_cannot_bypass_with_new_identifier(db_session,paid):
    s,p,a=paid;register(db_session,s,p)
    with pytest.raises(ValueError):register(db_session,s,p,bank_reference='CHANGED',bank_transaction_id='NEW')


def test_substitution_chain_void_and_correction_blocks(db_session,paid):
    s,p,a=paid;op=apply(db_session,s,p,**args(amount='150'));current=db_session.get(OwnerPayout,op.replacement_payout_id)
    r=register(db_session,s,p)
    assert r.payout_id==current.id and r.transfer_root_id==p.id
    assert balances.summary(db_session,s)['paid']==110
    with pytest.raises(ValueError):register(db_session,s,current)
    for kind in ['void','replace']:
        with pytest.raises(ValueError):apply(db_session,s,current,**args(kind))


def test_void_disallows_return(db_session,paid):
    s,p,a=paid;apply(db_session,s,p,**args('void'))
    with pytest.raises(ValueError):register(db_session,s,p)


def test_copropietor_and_shared_funds(db_session,paid,sample):
    s,p,a=paid;other=draft(db_session,sample,'b');service.close(db_session,other.id,other.fingerprint)
    other_before=balances.summary(db_session,other)['available']
    snap=deepcopy(s.snapshot);snap['totals'].update(funds_balance='50.00',prior_balance='0.00',payout_due='50.00',carry_forward='0.00')
    extra=OwnerSettlement(owner_id=s.owner_id,period_start=date(2026,10,1),period_end=date(2026,11,1),status='closed',closed_at=s.closed_at,selection=s.selection,fingerprint='synthetic',snapshot=snap,request_key=str(uuid4()))
    db_session.add(extra);db_session.commit();register(db_session,s,p)
    assert balances.summary(db_session,extra)['available']==190
    assert balances.summary(db_session,extra)['paid']==0
    assert balances.summary(db_session,other)['available']==other_before
    with pytest.raises(LookupError):returns.preview(db_session,other.id,p.id,**values())


def test_new_transfer_not_automatic_but_possible_after_return(db_session,paid):
    s,p,a=paid;register(db_session,s,p,amount='100')
    assert db_session.scalar(select(func.count()).select_from(OwnerPayout))==1
    service.payout(db_session,s.id,amount='200',effective_date=date(2026,9,23),bank_account_id=a.id,method='bank_transfer',request_key=str(uuid4()))
    assert balances.summary(db_session,s)['paid']==200


def test_stale_and_atomic_rollback(db_session,paid):
    s,p,a=paid;v=values();review=returns.preview(db_session,s.id,p.id,**v)
    register(db_session,s,p,amount='20')
    with pytest.raises(ValueError,match='cambiado'):returns.confirm(db_session,s.id,p.id,**v,request_key=str(uuid4()),expected=review['fingerprint'],confirmed=True)
    def fail(*_):raise RuntimeError('synthetic rollback')
    event.listen(OwnerPayoutReturn,'after_insert',fail)
    try:
        with pytest.raises(RuntimeError):register(db_session,s,p,amount='30')
    finally:event.remove(OwnerPayoutReturn,'after_insert',fail)
    assert balances.summary(db_session,s)['returned']==20

@pytest.mark.parametrize('same_key',[True,False])
def test_concurrency_idempotence(db_session,paid,same_key):
    s,p,a=paid;v=values(amount='60');review=returns.preview(db_session,s.id,p.id,**v);key=str(uuid4());sid,pid=s.id,p.id;engine=db_session.get_bind();db_session.rollback()
    def run(k):
        with Session(engine) as db:
            try:return returns.confirm(db,sid,pid,**v,request_key=k,expected=review['fingerprint'],confirmed=True).id
            except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(run,[key,key if same_key else str(uuid4())]))
    assert result[0]==result[1] if same_key else result.count(None)==1
    db_session.expire_all();assert db_session.scalar(select(func.count()).select_from(OwnerPayoutReturn))==1
    assert balances.summary(db_session,s)['paid']==40


def test_privacy_and_historical_pdf(db_session,paid,tmp_path):
    from backend.services.settlement_document_service import SettlementDocumentService
    from pypdf import PdfReader
    s,p,a=paid;docs=SettlementDocumentService(tmp_path/'docs');first=docs.generate(db_session,s.id)
    _,path=docs.download(db_session,s.id,first['version']);original=path.read_bytes();closed=deepcopy(s.snapshot)
    r=register(db_session,s,p,reason='Cuenta '+a.iban,bank_reference=a.iban)
    assert a.iban not in json.dumps(raw(r),default=str)
    second=docs.generate(db_session,s.id);_,newpath=docs.download(db_session,s.id,second['version'])
    assert path.read_bytes()==original and s.snapshot==closed and second['version']==first['version']+1
    text=' '.join(page.extract_text() for page in PdfReader(newpath).pages)
    assert 'DEVOLUCIONES BANCARIAS' in text and '140,00' in text


def test_compensation_guard(db_session,paid):
    s,p,a=paid;s.selection=dict(s.selection,billing=True);db_session.commit()
    with pytest.raises(ValueError,match='compensaciones'):register(db_session,s,p)


def test_closed_500_return_200(db_session,sample):
    from backend.models import PropertyOwnership
    from backend.models.owner_settlement import ManagementFeeTerms
    from backend.models.owner_bank_account import OwnerBankAccount
    for row in db_session.scalars(select(PropertyOwnership).where(PropertyOwnership.property_id==sample['property'].id)):
        if row.owner_id==sample['a'].id:row.ownership_percentage=100
        else:db_session.delete(row)
    for row in db_session.scalars(select(ManagementFeeTerms).where(ManagementFeeTerms.property_id==sample['property'].id)):row.percentage=0
    db_session.commit();s=draft(db_session,sample);service.close(db_session,s.id,s.fingerprint)
    a=OwnerBankAccount(owner_id=s.owner_id,account_holder_name='Synthetic',iban='ES9121000418450200051332',active=True,receives_settlements=True)
    db_session.add(a);db_session.commit()
    p=service.payout(db_session,s.id,amount='500',effective_date=date(2026,9,20),bank_account_id=a.id,method='bank_transfer',request_key=str(uuid4()))
    register(db_session,s,p,amount='200');b=balances.summary(db_session,s)
    assert s.status=='closed' and b['gross_paid']==500 and b['returned']==200 and b['paid']==300 and b['remaining']==200 and b['available']==200


def test_unique_bank_id_even_across_transfers(db_session,paid):
    s,p,a=paid;register(db_session,s,p,bank_transaction_id='BANK-UNIQUE')
    nextp=service.payout(db_session,s.id,amount='10',effective_date=date(2026,9,23),bank_account_id=a.id,method='bank_transfer',request_key=str(uuid4()))
    with pytest.raises(ValueError):register(db_session,s,nextp,amount='5',effective_date='2026-09-24',bank_transaction_id='bank-unique')


def test_inactive_account_and_receipt_confirmation(db_session,paid):
    s,p,a=paid;a.active=False;db_session.commit()
    v=values();review=returns.preview(db_session,s.id,p.id,**v);key=str(uuid4())
    with pytest.raises(ValueError):returns.confirm(db_session,s.id,p.id,**v,request_key=key,expected=review['fingerprint'],confirmed=False)
    r=returns.confirm(db_session,s.id,p.id,**v,request_key=key,expected=review['fingerprint'],confirmed=True,operator_id='synthetic-operator')
    assert r.operator_id=='synthetic-operator'
    with pytest.raises(ValueError):returns.confirm(db_session,s.id,p.id,**values(amount='41'),request_key=key,expected=review['fingerprint'],confirmed=True)
