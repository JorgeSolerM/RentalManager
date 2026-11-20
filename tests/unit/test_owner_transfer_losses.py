from uuid import uuid4
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import pytest
from sqlalchemy import select,func,event
from sqlalchemy.orm import Session
from backend.models.owner_transfer_regularization import OwnerTransferRegularizationOperation as Operation
from backend.services.owner_transfer_regularization_service import OwnerTransferRegularizationService
from tests.unit.test_owner_transfer_recoveries import sample,paid,register,extra,incidents,balances,service,draft,raw,bank_return,recover,recoveries,inputs,pay

losses=OwnerTransferRegularizationService()
def values(**changes):
    v=dict(kind='recognize',amount='40',responsible='pending',reason='Reconocimiento sintético',evidence='Documento sintético: reclamación infructuosa',evidence_reference='DOC-SYNTHETIC-1')
    v.update(changes);return v
def recognize(db,i,**changes):
    v=values(**changes);p=losses.preview(db,i.id,**v)
    return losses.confirm(db,i.id,**v,request_key=str(uuid4()),expected=p['fingerprint'],confirmed=True)
def economic(db,s):
    b=balances.summary(db,s)
    return {k:b[k] for k in ('paid','remaining','available','deficit','cash_used','pending_recovery','payout_blockers')}

@pytest.mark.parametrize('amount',['40','100'])
@pytest.mark.parametrize('responsible',['pending','manager','owner'])
def test_partial_full_responsibilities_without_economic_effect(db_session,paid,amount,responsible):
    s,p,a=paid;i=register(db_session,s,p);before=economic(db_session,s);closed=raw(s);original=raw(p)
    extra_values=dict(responsible_owner_id=s.owner_id,agreement='Acuerdo firmado sintético',authorized=True) if responsible=='owner' else {}
    op=recognize(db_session,i,amount=amount,responsible=responsible,**extra_values)
    assert economic(db_session,s)==before and raw(s)==closed and raw(p)==original
    state=losses.form(db_session,i.id)['loss'];assert Decimal(state['recognized'])==Decimal(amount) and Decimal(state['without_loss_recognition'])==100-Decimal(amount)
    assert state['responsibilities'][0]['responsible']==responsible and op.before_state['balances']==op.after_state['balances']

def test_duplicate_and_excess(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p);recognize(db_session,i,amount='60')
    for v in [dict(amount='60',evidence_reference='OTHER'),dict(amount='20'),dict(amount='20',evidence_reference='  doc-synthetic-1  ')]:
        with pytest.raises(ValueError):recognize(db_session,i,**v)
    recognize(db_session,i,amount='40',evidence_reference='DISTINCT-DOCUMENT-PART-2')
    with pytest.raises(ValueError):recognize(db_session,i,amount='0.01',evidence_reference='THIRD')

@pytest.mark.parametrize('missing',['agreement','authorized','responsible_owner_id'])
def test_owner_requires_explicit_agreement(db_session,paid,missing):
    s,p,a=paid;i=register(db_session,s,p);v=values(responsible='owner',responsible_owner_id=s.owner_id,agreement='Agreement',authorized=True);v.pop(missing)
    with pytest.raises(ValueError):losses.preview(db_session,i.id,**v)

def test_assign_once_and_history(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p);op=recognize(db_session,i);original=raw(op);before=economic(db_session,s)
    v=values(kind='responsibility',loss_id=op.id,responsible='manager');preview=losses.preview(db_session,i.id,**v);key=str(uuid4())
    for _ in range(2):losses.confirm(db_session,i.id,**v,request_key=key,expected=preview['fingerprint'],confirmed=True)
    assert raw(op)==original and economic(db_session,s)==before
    assert losses.form(db_session,i.id)['loss']['responsibilities'][0]['responsible']=='manager'
    with pytest.raises(ValueError):losses.preview(db_session,i.id,**v)

def test_prior_returns_and_recoveries(db_session,paid):
    s,p,a=paid;bank_return(db_session,s,p,amount='20');i=register(db_session,s,p,amount='80');recover(db_session,i,a,amount='30')
    with pytest.raises(ValueError):recognize(db_session,i,amount='51')
    before=economic(db_session,s);recognize(db_session,i,amount='50');assert economic(db_session,s)==before

def test_later_recovery_allowed_without_loss_reversal(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p);op=recognize(db_session,i,amount='100');original=raw(op)
    recover(db_session,i,a,amount='40');state=losses.form(db_session,i.id)['loss']
    assert state['later_recovery_pending'] and state['recognized']=='100.00' and state['overlap']=='40.00'
    assert raw(op)==original and balances.summary(db_session,s)['remaining']==200 and balances.summary(db_session,s)['available']==140
    with pytest.raises(ValueError):recognize(db_session,i,amount='1',evidence_reference='NEW')

def test_coprop_funds_and_owner_responsibility(db_session,paid,sample):
    s,p,a=paid;other=draft(db_session,sample,'b');service.close(db_session,other.id,other.fingerprint)
    i=register(db_session,s,p,**extra(s,p,allocations={str(s.owner_id):'40',str(other.owner_id):'40'}))
    before=[economic(db_session,x) for x in (s,other)]
    recognize(db_session,i,responsible='owner',responsible_owner_id=other.owner_id,agreement='Specific agreement',authorized=True)
    assert [economic(db_session,x) for x in (s,other)]==before
    with pytest.raises(ValueError):recognize(db_session,i,amount='1',responsible='owner',responsible_owner_id=other.owner_id,agreement='Specific agreement',authorized=True,evidence_reference='SECOND')

@pytest.mark.parametrize('unknown',[True,False])
def test_pending_attribution_and_deficit_preserved(db_session,paid,unknown):
    s,p,a=paid;i=register(db_session,s,p,**extra(s,p,amount='300',allocations={} if unknown else {str(s.owner_id):'300'}));before=economic(db_session,s)
    recognize(db_session,i,amount='300',responsible='manager');assert economic(db_session,s)==before
    assert before['payout_blockers'] if unknown else before['deficit']==200

def test_credited_receipt_is_not_automatically_loss(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p,kind='wrong_account',recipient_owner_id=s.owner_id,receipt_accredited=True)
    with pytest.raises(ValueError):recognize(db_session,i)

def test_idempotence_stale_and_rollback(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p);v=values();p1=losses.preview(db_session,i.id,**v);key=str(uuid4())
    for _ in range(2):losses.confirm(db_session,i.id,**v,request_key=key,expected=p1['fingerprint'],confirmed=True)
    assert db_session.scalar(select(func.count()).select_from(Operation))==1
    with pytest.raises(ValueError):losses.confirm(db_session,i.id,**values(amount='20'),request_key=key,expected=p1['fingerprint'],confirmed=True)
    v=values(amount='10',evidence_reference='SECOND');p2=losses.preview(db_session,i.id,**v);recover(db_session,i,a,amount='10')
    with pytest.raises(ValueError):losses.confirm(db_session,i.id,**v,request_key=str(uuid4()),expected=p2['fingerprint'],confirmed=True)
    v=values(kind='responsibility',loss_id=1,responsible='manager');p3=losses.preview(db_session,i.id,**v)
    def fail(*args):raise RuntimeError('Synthetic rollback')
    event.listen(Operation,'after_insert',fail)
    try:
        with pytest.raises(RuntimeError):losses.confirm(db_session,i.id,**v,request_key=str(uuid4()),expected=p3['fingerprint'],confirmed=True)
    finally:event.remove(Operation,'after_insert',fail)
    assert db_session.scalar(select(func.count()).select_from(Operation))==1

@pytest.mark.parametrize('same_key',[True,False])
def test_concurrent_recognition(db_session,paid,same_key):
    s,p,a=paid;i=register(db_session,s,p);iid=i.id;v=values(amount='80');pr=losses.preview(db_session,iid,**v);key=str(uuid4());engine=db_session.get_bind();db_session.rollback()
    def run(k):
        with Session(engine) as db:
            try:return losses.confirm(db,iid,**v,request_key=k,expected=pr['fingerprint'],confirmed=True).id
            except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,[key,key if same_key else str(uuid4())]))
    assert results[0]==results[1] if same_key else results.count(None)==1
    assert db_session.scalar(select(func.count()).select_from(Operation))==1

def test_concurrent_recovery_and_recognition(db_session,paid):
    s,p,a=paid;i=register(db_session,s,p);iid=i.id;v=values(amount='100');rv=inputs(a,amount='40');pr=losses.preview(db_session,iid,**v);rr=recoveries.preview(db_session,iid,**rv);engine=db_session.get_bind();db_session.rollback()
    def run(kind):
        with Session(engine) as db:
            try:
                if kind=='loss':losses.confirm(db,iid,**v,request_key=str(uuid4()),expected=pr['fingerprint'],confirmed=True)
                else:recoveries.confirm(db,iid,**rv,request_key=str(uuid4()),expected=rr['fingerprint'],confirmed=True)
                return True
            except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(run,['loss','recovery']))==1

def test_pdf_unchanged(db_session,paid,tmp_path):
    from backend.services.settlement_document_service import SettlementDocumentService
    s,p,a=paid;i=register(db_session,s,p);docs=SettlementDocumentService(tmp_path/'docs');doc=docs.generate(db_session,s.id);_,path=docs.download(db_session,s.id,doc['version']);content=path.read_bytes();closed=deepcopy(s.snapshot)
    recognize(db_session,i);new=docs.generate(db_session,s.id)
    assert new['version']==doc['version'] and path.read_bytes()==content and s.snapshot==closed


def test_owner_responsibility_excludes_already_recovered_share(db_session,paid,sample):
    s,p,a=paid;other=draft(db_session,sample,'b');service.close(db_session,other.id,other.fingerprint)
    i=register(db_session,s,p,**extra(s,p,allocations={str(s.owner_id):'40',str(other.owner_id):'40'}))
    recover(db_session,i,a,amount='30',allocations={str(s.owner_id):'30'})
    with pytest.raises(ValueError):recognize(db_session,i,amount='20',responsible='owner',responsible_owner_id=s.owner_id,agreement='Specific agreement',authorized=True)
    recognize(db_session,i,amount='10',responsible='owner',responsible_owner_id=s.owner_id,agreement='Specific agreement',authorized=True)


def test_evidence_does_not_copy_full_bank_accounts(db_session,paid):
    import json
    s,p,a=paid;i=register(db_session,s,p)
    row=recognize(db_session,i,responsible='owner',responsible_owner_id=s.owner_id,agreement='Agreement '+a.iban,authorized=True,evidence='Document '+a.iban)
    assert a.iban not in json.dumps([row.before_state,row.after_state,row.evidence,row.agreement])
