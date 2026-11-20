from datetime import date
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import pytest
from sqlalchemy import select,func,event
from sqlalchemy.orm import Session
from backend.models.owner_transfer_recovery import OwnerTransferRecovery as Recovery,OwnerRecoveryAttribution,OwnerBankCreditIdentity,OwnerRecoveryReturnLink,OwnerPayoutReview
from backend.models.owner_payout_return import OwnerPayoutReturn
from backend.models.owner_settlement import OwnerPayout
from backend.services.owner_transfer_recovery_service import OwnerTransferRecoveryService
from backend.services.owner_payout_review_service import OwnerPayoutReviewService
from tests.unit.test_owner_transfer_incidents import sample,paid,register,extra,incidents,balances,service,draft,apply,args,raw,bank_return
recoveries=OwnerTransferRecoveryService();reviewed=OwnerPayoutReviewService()


def inputs(a,**changes):
    v=dict(amount='40',effective_date='2026-09-24',receiving_iban=a.iban,bank_reference='SYNTHETIC CREDIT',bank_transaction_id='CREDIT-1',reason='Recuperación sintética',evidence='Extracto sintético',received=True)
    v.update(changes);return v


def recover(db,i,a,**changes):
    v=inputs(a,**changes);p=recoveries.preview(db,i.id,**v)
    return recoveries.confirm(db,i.id,**v,request_key=str(uuid4()),expected=p['fingerprint'],confirmed=True)


def payinputs(a,**changes):
    v=dict(amount='40',effective_date='2026-09-25',bank_account_id=str(a.id),reference='SYNTHETIC NEW PAYOUT',reason='Nuevo pago correcto',paid=True)
    v.update(changes);return v


def pay(db,s,a,**changes):
    v=payinputs(a,**changes);p=reviewed.preview(db,s.id,**v)
    return reviewed.confirm(db,s.id,**v,request_key=str(uuid4()),expected=p['fingerprint'],confirmed=True)


@pytest.mark.parametrize('amount',['40','100'])
def test_partial_full_and_new_payment(db_session,paid,amount):
    s,p,a=paid;original=raw(p);closed=raw(s);i=register(db_session,s,p)
    recover(db_session,i,a,amount=amount);b=balances.summary(db_session,s)
    assert b['paid']==0 and b['remaining']==200 and b['available']==100+int(amount) and b['pending_recovery']==100-int(amount)
    pay(db_session,s,a,amount=amount);b=balances.summary(db_session,s)
    assert b['paid']==int(amount) and b['remaining']==200-int(amount) and b['available']==100
    assert raw(p)==original and raw(s)==closed


def test_successive_and_excess(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p)
    for n,amount in enumerate(['20','30','50']):recover(db_session,i,a,amount=amount,bank_transaction_id='SUCCESSIVE-'+str(n))
    assert recoveries.form(db_session,i.id)['maximum']==0
    with pytest.raises(ValueError):recover(db_session,i,a,amount='0.01',bank_transaction_id='EXCESS')
    assert balances.summary(db_session,s)['available']==200


def test_credited_same_owner_return_reopens_obligation(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p,kind='wrong_account',recipient_owner_id=s.owner_id,receipt_accredited=True)
    recover(db_session,i,a);b=balances.summary(db_session,s)
    assert b['paid']==60 and b['remaining']==140 and b['available']==140


def test_deficit_reduced_before_available(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p,**extra(s,p,amount='300',allocations={str(s.owner_id):'300'}))
    recover(db_session,i,a,amount='80');b=balances.summary(db_session,s)
    assert b['deficit']==120 and b['available']==0 and b['remaining']==100
    recover(db_session,i,a,amount='140',bank_transaction_id='CREDIT-2');b=balances.summary(db_session,s)
    assert b['deficit']==0 and b['available']==20 and b['remaining']==100
    with pytest.raises(ValueError):pay(db_session,s,a,amount='21')


def test_unknown_allocation_then_audited_attribution(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p,**extra(s,p,allocations={}))
    r=recover(db_session,i,a,amount='30');b=balances.summary(db_session,s)
    assert b['available']==0 and b['recovered_funds']==0 and b['payout_blockers']
    v=incidents.attribution_preview(db_session,i.id,allocations={str(s.owner_id):'80'},reason='Synthetic attribution')
    incidents.attribute(db_session,i.id,allocations={str(s.owner_id):'80'},reason='Synthetic attribution',request_key=str(uuid4()),expected=v['fingerprint'],confirmed=True)
    assert balances.summary(db_session,s)['available']==0
    v=recoveries.attribution_preview(db_session,r.id,reason='Recovered funds identified');key=str(uuid4())
    for _ in range(2):recoveries.attribute(db_session,r.id,allocations={},reason='Recovered funds identified',request_key=key,expected=v['fingerprint'],confirmed=True)
    b=balances.summary(db_session,s);assert b['available']==50 and b['recovered_funds']==30 and not b['payout_blockers']
    with pytest.raises(ValueError):recoveries.attribution_preview(db_session,r.id,reason='Again')


def test_coprop_explicit_distribution_and_limits(db_session,paid,sample):
    s,p,a=paid;s2=draft(db_session,sample,'b');service.close(db_session,s2.id,s2.fingerprint)
    parts={str(s.owner_id):'40',str(s2.owner_id):'40'};i=register(db_session,s,p,**extra(s,p,allocations=parts))
    with pytest.raises(ValueError):recover(db_session,i,a,amount='30')
    recover(db_session,i,a,amount='30',allocations={str(s.owner_id):'20',str(s2.owner_id):'10'})
    assert balances.summary(db_session,s)['available']==80 and balances.summary(db_session,s2)['available']==170
    with pytest.raises(ValueError):recover(db_session,i,a,amount='30',allocations={str(s.owner_id):'30'},bank_transaction_id='OTHER')


def test_previous_return_documentary_link_and_no_double_credit(db_session,paid):
    s,p,a=paid;ret=bank_return(db_session,s,p,amount='40');i=register(db_session,s,p,amount='60')
    before=balances.summary(db_session,s);v=recoveries.link_preview(db_session,i.id,return_id=ret.id,reason='Documento histórico');key=str(uuid4())
    for _ in range(2):recoveries.link_return(db_session,i.id,return_id=ret.id,reason='Documento histórico',request_key=key,expected=v['fingerprint'],confirmed=True)
    assert balances.summary(db_session,s)['available']==before['available']==140
    recover(db_session,i,a,amount='30');b=balances.summary(db_session,s)
    assert b['available']==170 and b['paid']==0 and b['pending_recovery']==30
    assert recoveries.form(db_session,i.id)['previous_returned']==40


@pytest.mark.parametrize('with_id',[True,False])
def test_cross_circuit_duplicate_both_directions(db_session,paid,with_id):
    s,p,a=paid;ret=bank_return(db_session,s,p,amount='10',bank_transaction_id='CROSS' if with_id else None,effective_date='2026-09-24')
    i=register(db_session,s,p,amount='90')
    with pytest.raises(ValueError):recover(db_session,i,a,amount='10',bank_transaction_id='CROSS' if with_id else None,bank_reference='CHANGED TEXT')
    recover(db_session,i,a,amount='20',bank_transaction_id='NEW' if with_id else None)
    p2=service.payout(db_session,s.id,amount='20',effective_date=date(2026,9,23),bank_account_id=a.id,method='bank_transfer',request_key=str(uuid4()))
    with pytest.raises(ValueError):bank_return(db_session,s,p2,amount='20',bank_transaction_id='NEW' if with_id else None,effective_date='2026-09-24')


def test_idempotence_stale_and_rollback(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p);v=inputs(a);preview=recoveries.preview(db_session,i.id,**v);key=str(uuid4())
    for _ in range(2):recoveries.confirm(db_session,i.id,**v,request_key=key,expected=preview['fingerprint'],confirmed=True)
    assert db_session.scalar(select(func.count()).select_from(Recovery))==1
    with pytest.raises(ValueError):recover(db_session,i,a)
    v2=inputs(a,amount='10',bank_transaction_id='SECOND');stale=recoveries.preview(db_session,i.id,**v2);pay(db_session,s,a,amount='10')
    with pytest.raises(ValueError):recoveries.confirm(db_session,i.id,**v2,request_key=str(uuid4()),expected=stale['fingerprint'],confirmed=True)
    def fail(*args):raise RuntimeError('Synthetic rollback')
    event.listen(OwnerBankCreditIdentity,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError):recover(db_session,i,a,amount='10',bank_transaction_id='ROLLBACK')
    finally:event.remove(OwnerBankCreditIdentity,'before_insert',fail)
    assert db_session.scalar(select(func.count()).select_from(Recovery))==1


@pytest.mark.parametrize('same_key',[True,False])
def test_concurrent_recoveries(db_session,paid,same_key):
    s,p,a=paid;i=register(db_session,s,p);iid=i.id;v=inputs(a,amount='80');preview=recoveries.preview(db_session,iid,**v);key=str(uuid4());engine=db_session.get_bind();db_session.rollback()
    def run(k):
        with Session(engine) as db:
            try:return recoveries.confirm(db,iid,**v,request_key=k,expected=preview['fingerprint'],confirmed=True).id
            except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,[key,key if same_key else str(uuid4())]))
    assert results[0]==results[1] if same_key else results.count(None)==1
    assert db_session.scalar(select(func.count()).select_from(Recovery))==1


def test_recovery_concurrent_with_new_payout(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p);iid=i.id;sid=s.id;rv=inputs(a,amount='10');pv=payinputs(a,amount='10');rp=recoveries.preview(db_session,iid,**rv);pp=reviewed.preview(db_session,sid,**pv);engine=db_session.get_bind();db_session.rollback()
    def run(kind):
        with Session(engine) as db:
            try:
                if kind=='recovery':recoveries.confirm(db,iid,**rv,request_key=str(uuid4()),expected=rp['fingerprint'],confirmed=True)
                else:reviewed.confirm(db,sid,**pv,request_key=str(uuid4()),expected=pp['fingerprint'],confirmed=True)
                return True
            except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(run,['recovery','payout']))==1


def test_distinct_same_day_payout_identity(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p);recover(db_session,i,a,amount='100',effective_date='2026-09-20')
    with pytest.raises(ValueError):pay(db_session,s,a,amount='100',effective_date='2026-09-20')
    p2=pay(db_session,s,a,amount='100',effective_date='2026-09-20',source_iban=a.iban,bank_transaction_id='REAL-NEW',previous_payout_id=str(p.id),previous_bank_id='REAL-OLD')
    assert p2.id!=p.id and balances.summary(db_session,s)['paid']==100
    with pytest.raises(ValueError):pay(db_session,s,a,amount='100',effective_date='2026-09-21',source_iban=a.iban,bank_transaction_id='REAL-NEW')


def test_historical_pdf_and_corrections_preserved(db_session,paid,tmp_path):
    from backend.services.settlement_document_service import SettlementDocumentService
    s,p,a=paid;docs=SettlementDocumentService(tmp_path/'docs');doc=docs.generate(db_session,s.id);_,path=docs.download(db_session,s.id,doc['version']);content=path.read_bytes();closed=deepcopy(s.snapshot);original=raw(p)
    i=register(db_session,s,p);recover(db_session,i,a);new=docs.generate(db_session,s.id)
    assert new['version']==doc['version']+1 and path.read_bytes()==content and s.snapshot==closed and raw(p)==original
    with pytest.raises(ValueError):apply(db_session,s,p,**args('void'))
    assert db_session.scalar(select(func.count()).select_from(OwnerPayoutReturn))==0


@pytest.mark.parametrize('change',[{'received':False},{'amount':'0'},{'amount':'101'},{'reason':''},{'evidence':''},{'receiving_iban':''},{'effective_date':'bad'},{'effective_date':'2026-09-19'}])
def test_invalid_recovery(db_session,paid,change):
    s,p,a=paid;i=register(db_session,s,p)
    with pytest.raises(ValueError):recover(db_session,i,a,**change)



def test_recovered_real_duplicate_keeps_valid_original_payment(db_session,paid):
    s,p,a=paid;original=raw(p)
    i=register(db_session,s,p,**extra(s,p,kind='duplicate',amount='100',allocations={str(s.owner_id):'100'},duplicate_of_id=p.id,effective_date=str(p.effective_date),source_iban=a.iban,destination_iban=a.iban,original_bank_id='DUP-ORIGINAL',bank_transaction_id='DUP-EXTRA'))
    recover(db_session,i,a,amount='100');b=balances.summary(db_session,s)
    assert b['paid']==100 and b['remaining']==100 and b['available']==100 and b['pending_recovery']==0 and raw(p)==original


def test_distinct_incoming_ids_and_historical_inactive_account(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p);a.active=False;db_session.commit()
    recover(db_session,i,a,amount='20',bank_transaction_id='UNIQUE-1')
    recover(db_session,i,a,amount='20',bank_transaction_id='UNIQUE-2')
    with pytest.raises(ValueError):recover(db_session,i,a,amount='10',effective_date='2026-09-25',bank_transaction_id='UNIQUE-1')
    with pytest.raises(ValueError):pay(db_session,s,a,amount='10')
    assert balances.summary(db_session,s)['recovered_funds']==40


def test_payout_registration_rollback_and_stale_bank_account(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p);recover(db_session,i,a)
    v=payinputs(a);view=reviewed.preview(db_session,s.id,**v);a.account_holder_name='Updated synthetic holder';db_session.commit()
    with pytest.raises(ValueError):reviewed.confirm(db_session,s.id,**v,request_key=str(uuid4()),expected=view['fingerprint'],confirmed=True)
    def fail(*args):raise RuntimeError('Synthetic payout rollback')
    event.listen(OwnerPayoutReview,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError):pay(db_session,s,a)
    finally:event.remove(OwnerPayoutReview,'before_insert',fail)
    assert db_session.scalar(select(func.count()).select_from(OwnerPayout))==1


@pytest.mark.parametrize('same_key',[True,False])
def test_concurrent_recovery_attribution(db_session,paid,same_key):
    s,p,a=paid;i=register(db_session,s,p,**extra(s,p,allocations={}))
    r=recover(db_session,i,a,amount='20');rid=r.id
    view=incidents.attribution_preview(db_session,i.id,allocations={str(s.owner_id):'80'},reason='Source')
    incidents.attribute(db_session,i.id,allocations={str(s.owner_id):'80'},reason='Source',request_key=str(uuid4()),expected=view['fingerprint'],confirmed=True)
    view=recoveries.attribution_preview(db_session,rid,reason='Recovered ownership');key=str(uuid4());engine=db_session.get_bind();db_session.rollback()
    def run(k):
        with Session(engine) as db:
            try:return recoveries.attribute(db,rid,allocations={},reason='Recovered ownership',request_key=k,expected=view['fingerprint'],confirmed=True).id
            except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,[key,key if same_key else str(uuid4())]))
    assert results[0]==results[1] if same_key else results.count(None)==1
    assert db_session.scalar(select(func.count()).select_from(OwnerRecoveryAttribution))==1



def test_missing_id_cannot_evade_by_changing_account(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p);recover(db_session,i,a,amount='20',bank_transaction_id=None)
    # Valid checksum, exclusively synthetic alternate destination.
    domestic='00000000000000000099';iban='ES'+str(98-int(domestic+'142800')%97).zfill(2)+domestic
    with pytest.raises(ValueError):recover(db_session,i,a,amount='20',bank_transaction_id=None,receiving_iban=iban,bank_reference='Different free text')



def test_core_payout_cannot_disagree_with_review(db_session,paid):
    s,p,a=paid;v=payinputs(a,amount='10');view=reviewed.preview(db_session,s.id,**v)
    with pytest.raises(ValueError):service.payout(db_session,s.id,amount='20',effective_date=date(2026,9,25),bank_account_id=a.id,method='bank_transfer',reference=v['reference'],request_key=str(uuid4()),reviewed=dict(inputs=v,expected=view['fingerprint']))
    assert db_session.scalar(select(func.count()).select_from(OwnerPayout))==1
