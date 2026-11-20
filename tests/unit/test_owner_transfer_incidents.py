from datetime import date
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import pytest
from sqlalchemy import select,func,event
from sqlalchemy.orm import Session
from backend.models.owner_transfer_incident import OwnerTransferIncident as Incident,OwnerTransferOutflow as Outflow,OwnerTransferIncidentOperation as Operation
from backend.models.owner_payout_return import OwnerPayoutReturn
from backend.models.owner_settlement import OwnerPayout
from backend.services.owner_transfer_incident_service import OwnerTransferIncidentService
from tests.unit.test_owner_payout_corrections import sample,paid,balances,corrections,args,apply,raw,draft,service
from tests.unit.test_owner_payout_returns import register as bank_return,returns,values as return_values
incidents=OwnerTransferIncidentService()

def values(s,p,**changes):
    data=dict(source_kind='payout',payout_id=p.id,kind='unknown_recipient',amount='100',reason='Incidencia sintética',evidence='Extracto sintético con salida efectiva',executed=True)
    data.update(changes);return data

def register(db,s,p,**changes):
    data=values(s,p,**changes);review=incidents.preview(db,s.id,**data)
    return incidents.confirm(db,s.id,**data,request_key=str(uuid4()),expected=review['fingerprint'],confirmed=True)

def extra(s,p,**changes):
    v=dict(source_kind='extraordinary',payout_id=None,amount='80',effective_date='2026-09-23',reference='SYNTHETIC-OUT',bank_transaction_id='SYNTHETIC-1',allocations={str(s.owner_id):'80'})
    v.update(changes);return v

@pytest.mark.parametrize('credited',[True,False])
def test_wrong_account_same_owner(db_session,paid,credited):
    s,p,a=paid;before=raw(p);closed=raw(s)
    incident=register(db_session,s,p,kind='wrong_account',recipient_owner_id=s.owner_id,receipt_accredited=credited)
    b=balances.summary(db_session,s)
    assert b['paid']==(100 if credited else 0) and b['remaining']==(100 if credited else 200)
    assert b['available']==100 and b['pending_recovery']==(0 if credited else 100)
    assert raw(p)==before and raw(s)==closed
    assert db_session.scalar(select(func.count()).select_from(Outflow))==0
    assert db_session.scalar(select(func.count()).select_from(OwnerPayoutReturn))==0


def test_wrong_owner_no_credit_to_recipient(db_session,paid,sample):
    s,p,a=paid;other=draft(db_session,sample,'b');service.close(db_session,other.id,other.fingerprint)
    before=balances.summary(db_session,other)
    register(db_session,s,p,kind='wrong_recipient',recipient_owner_id=other.owner_id)
    after=balances.summary(db_session,other)
    assert after['paid']==before['paid']==0 and after['available']==before['available']==200
    assert balances.summary(db_session,s)['paid']==0 and balances.summary(db_session,s)['available']==100


def test_real_duplicate_counted_once_and_not_valid_payment(db_session,paid):
    s,p,a=paid
    incident=register(db_session,s,p,**extra(s,p,kind='duplicate',amount='100',allocations={str(s.owner_id):'100'},effective_date=str(p.effective_date),destination_iban=a.iban,source_iban=a.iban,duplicate_of_id=p.id,original_bank_id='SYNTHETIC-ORIGINAL',bank_transaction_id='SYNTHETIC-SECOND'))
    b=balances.summary(db_session,s)
    assert b['paid']==100 and b['remaining']==100 and b['cash_used']==200 and b['available']==0 and b['pending_recovery']==100
    assert db_session.scalar(select(func.count()).select_from(OwnerPayout))==1
    with pytest.raises(ValueError):register(db_session,s,p,**extra(s,p,bank_transaction_id='SYNTHETIC-SECOND'))
    with pytest.raises(ValueError):service.payout(db_session,s.id,amount='100',effective_date=p.effective_date,bank_account_id=a.id,method='bank_transfer',request_key=str(uuid4()))


def test_deficit_is_visible(db_session,paid):
    s,p,a=paid;register(db_session,s,p,**extra(s,p,amount='300',allocations={str(s.owner_id):'300'}))
    b=balances.summary(db_session,s);assert b['deficit']==200 and b['available']==0 and b['remaining']==100


def test_global_pending_attribution_and_audit(db_session,paid,sample):
    s,p,a=paid;other=draft(db_session,sample,'b');service.close(db_session,other.id,other.fingerprint)
    incident=register(db_session,s,p,**extra(s,p,allocations={}))
    for settlement in (s,other):assert balances.summary(db_session,settlement)['payout_blockers']
    with pytest.raises(ValueError):service.payout(db_session,s.id,amount='1',effective_date=p.effective_date,bank_account_id=a.id,method='bank_transfer',request_key=str(uuid4()))
    allocations={str(s.owner_id):'40',str(other.owner_id):'40'}
    review=incidents.attribution_preview(db_session,incident.id,allocations=allocations,reason='Evidencia sintética de custodia')
    key=str(uuid4())
    for _ in range(2):incidents.attribute(db_session,incident.id,allocations=allocations,reason='Evidencia sintética de custodia',request_key=key,expected=review['fingerprint'],confirmed=True)
    assert balances.summary(db_session,s)['available']==60 and balances.summary(db_session,other)['available']==160
    assert not balances.summary(db_session,s)['payout_blockers']
    with pytest.raises(ValueError):incidents.attribution_preview(db_session,incident.id,allocations=allocations,reason='Reatribuir')
    assert len(incidents.detail(db_session,incident.id)['history'])==2


def test_scoped_block_does_not_change_other_owner_rights(db_session,paid,sample):
    s,p,a=paid;other=draft(db_session,sample,'b');service.close(db_session,other.id,other.fingerprint)
    register(db_session,s,p,**extra(s,p,allocations={},scope=[s.owner_id]))
    assert balances.summary(db_session,s)['payout_blockers']
    assert not balances.summary(db_session,other)['payout_blockers']


def test_substitution_and_previous_returns(db_session,paid):
    s,p,a=paid;op=apply(db_session,s,p,**args(amount='150'));active=db_session.get(OwnerPayout,op.replacement_payout_id)
    bank_return(db_session,s,active,amount='40')
    with pytest.raises(ValueError):register(db_session,s,p,amount='111')
    register(db_session,s,p,amount='110');b=balances.summary(db_session,s)
    assert b['paid']==0 and b['returned']==40 and b['available']==90 and b['pending_recovery']==110
    with pytest.raises(ValueError):apply(db_session,s,active,**args('void'))
    with pytest.raises(ValueError):bank_return(db_session,s,active,amount='10')
    assert db_session.scalar(select(func.count()).select_from(OwnerPayoutReturn))==1

@pytest.mark.parametrize('same_key',[True,False])
def test_concurrent_registration(db_session,paid,same_key):
    s,p,a=paid;v=values(s,p);review=incidents.preview(db_session,s.id,**v);sid=s.id;key=str(uuid4());engine=db_session.get_bind();db_session.rollback()
    def run(k):
        with Session(engine) as db:
            try:return incidents.confirm(db,sid,**v,request_key=k,expected=review['fingerprint'],confirmed=True).id
            except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,[key,key if same_key else str(uuid4())]))
    assert results[0]==results[1] if same_key else results.count(None)==1
    assert db_session.scalar(select(func.count()).select_from(Incident))==1


def test_stale_and_atomic_outflow_rollback(db_session,paid):
    s,p,a=paid;v=values(s,p,**extra(s,p));review=incidents.preview(db_session,s.id,**v)
    service.payout(db_session,s.id,amount='10',effective_date=p.effective_date,bank_account_id=a.id,method='bank_transfer',request_key=str(uuid4()))
    with pytest.raises(ValueError):incidents.confirm(db_session,s.id,**v,request_key=str(uuid4()),expected=review['fingerprint'],confirmed=True)
    def fail(*_):raise RuntimeError('synthetic failure')
    event.listen(Operation,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError):register(db_session,s,p,**extra(s,p))
    finally:event.remove(Operation,'before_insert',fail)
    assert db_session.scalar(select(func.count()).select_from(Incident))==0
    assert db_session.scalar(select(func.count()).select_from(Outflow))==0


def test_closed_pdf_preserved_and_no_fictitious_income(db_session,paid,tmp_path):
    from backend.services.settlement_document_service import SettlementDocumentService
    s,p,a=paid;docs=SettlementDocumentService(tmp_path/'docs');artifact=docs.generate(db_session,s.id)
    _,path=docs.download(db_session,s.id,artifact['version']);content=path.read_bytes();snapshot=deepcopy(s.snapshot)
    register(db_session,s,p);new=docs.generate(db_session,s.id)
    assert path.read_bytes()==content and s.snapshot==snapshot and new['version']==artifact['version']+1
    assert db_session.scalar(select(func.count()).select_from(OwnerPayoutReturn))==0

@pytest.mark.parametrize('change',[{'executed':False},{'reason':''},{'evidence':''},{'amount':'0'},{'amount':'101'},{'receipt_accredited':True},{'payout_id':999999},{'source_kind':'bad'}])
def test_invalid_inputs(db_session,paid,change):
    s,p,a=paid
    with pytest.raises(ValueError):register(db_session,s,p,**change)


def test_extra_bank_identity_and_fallback_duplicates(db_session,paid):
    s,p,a=paid;register(db_session,s,p,**extra(s,p,bank_transaction_id=None))
    with pytest.raises(ValueError):register(db_session,s,p,**extra(s,p,reference='different reference',bank_transaction_id='NEW'))


def test_existing_void_and_compensations_blocked(db_session,paid):
    s,p,a=paid;apply(db_session,s,p,**args('void'))
    with pytest.raises(ValueError):register(db_session,s,p)
    s.selection=dict(s.selection,billing=True);db_session.commit()
    with pytest.raises(ValueError):register(db_session,s,p,**extra(s,p))


def test_stale_attribution_after_new_payout(db_session,paid):
    s,p,a=paid;incident=register(db_session,s,p,**extra(s,p,allocations={},scope=[s.owner_id]))
    allocations={str(s.owner_id):'80'};view=incidents.attribution_preview(db_session,incident.id,allocations=allocations,reason='Synthetic')
    # Another known outgoing event is still recordable even while ordinary payouts are blocked.
    register(db_session,s,p,**extra(s,p,amount='20',allocations={str(s.owner_id):'20'},bank_transaction_id='ANOTHER'))
    with pytest.raises(ValueError,match='cambiado'):incidents.attribute(db_session,incident.id,allocations=allocations,reason='Synthetic',request_key=str(uuid4()),expected=view['fingerprint'],confirmed=True)


def test_inactive_account_and_privacy(db_session,paid):
    s,p,a=paid;a.active=False;db_session.commit()
    incident=register(db_session,s,p,kind='wrong_account',recipient_owner_id=s.owner_id,reason='Cuenta '+a.iban.lower(),evidence='Cuenta '+a.iban)
    detail=incidents.detail(db_session,incident.id)
    history=json.dumps([raw(x) for x in detail['history']],default=str)
    assert a.iban not in history and a.iban.lower() not in history
    assert a.iban not in incident.evidence and a.iban.lower() not in incident.reason


def test_attribute_rollback(db_session,paid):
    s,p,a=paid;incident=register(db_session,s,p,**extra(s,p,allocations={}))
    allocations={str(s.owner_id):'80'};view=incidents.attribution_preview(db_session,incident.id,allocations=allocations,reason='Synthetic')
    def fail(*_):raise RuntimeError('synthetic rollback')
    event.listen(Operation,'after_insert',fail)
    try:
        with pytest.raises(RuntimeError):incidents.attribute(db_session,incident.id,allocations=allocations,reason='Synthetic',request_key=str(uuid4()),expected=view['fingerprint'],confirmed=True)
    finally:event.remove(Operation,'after_insert',fail)
    assert not incidents.detail(db_session,incident.id)['state']['allocations']


def test_ambiguous_duplicate_requires_distinct_bank_evidence(db_session,paid):
    s,p,a=paid
    for changes in [dict(original_bank_id=None),dict(bank_transaction_id='SAME',original_bank_id='SAME'),dict(source_iban=None)]:
        inputs=extra(s,p,kind='duplicate',duplicate_of_id=p.id,amount='100',allocations={str(s.owner_id):'100'},effective_date=str(p.effective_date),destination_iban=a.iban,source_iban=a.iban,bank_transaction_id='NEW',original_bank_id='OLD');inputs.update(changes)
        with pytest.raises(ValueError):register(db_session,s,p,**inputs)


@pytest.mark.parametrize('same_key',[True,False])
def test_concurrent_attribution(db_session,paid,same_key):
    s,p,a=paid;incident=register(db_session,s,p,**extra(s,p,allocations={}))
    iid=incident.id;allocation={str(s.owner_id):'80'}
    view=incidents.attribution_preview(db_session,iid,allocations=allocation,reason='Synthetic concurrent attribution')
    key=str(uuid4());engine=db_session.get_bind();db_session.rollback()
    def run(k):
        with Session(engine) as db:
            try:return incidents.attribute(db,iid,allocations=allocation,reason='Synthetic concurrent attribution',request_key=k,expected=view['fingerprint'],confirmed=True).id
            except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,[key,key if same_key else str(uuid4())]))
    assert results[0]==results[1] if same_key else results.count(None)==1
    assert db_session.scalar(select(func.count()).select_from(Operation).where(Operation.incident_id==iid,Operation.kind=='attribute'))==1
