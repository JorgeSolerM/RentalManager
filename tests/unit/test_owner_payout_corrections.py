from datetime import date
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import pytest
from sqlalchemy import select,func,event
from sqlalchemy.orm import Session
from backend.models.owner_settlement import OwnerPayout,OwnerSettlement
from backend.models.owner_bank_account import OwnerBankAccount
from backend.models.owner_payout_correction import OwnerPayoutCorrectionOperation as Operation
from backend.services.owner_payout_correction_service import OwnerPayoutCorrectionService,raw
from backend.services.owner_payout_balance_service import OwnerPayoutBalanceService
from tests.unit.test_owner_settlement_service import sample,draft,service

corrections=OwnerPayoutCorrectionService();balances=OwnerPayoutBalanceService()

@pytest.fixture
def paid(db_session,sample):
    s=draft(db_session,sample);service.close(db_session,s.id,s.fingerprint)
    account=OwnerBankAccount(owner_id=s.owner_id,account_holder_name='Cuenta sintética',iban='ES9121000418450200051332',active=True,receives_settlements=True)
    db_session.add(account);db_session.commit()
    p=service.payout(db_session,s.id,amount='100',effective_date=date(2026,9,20),bank_account_id=account.id,method='bank_transfer',reference='SYNTHETIC',request_key=str(uuid4()))
    return s,p,account

def args(kind='replace',amount='150',**changes):
    result=dict(kind=kind,reason='Rectificación sintética')
    if kind=='void':result['no_transfer']=True
    else:result.update(amount=amount,effective_date='2026-09-20',reference='SYNTHETIC',same_transfer=True)
    result.update(changes);return result

def apply(db,s,p,**values):
    view=corrections.preview(db,s.id,p.id,**values)
    return corrections.confirm(db,s.id,p.id,**values,request_key=str(uuid4()),expected=view['fingerprint'],confirmed=True)

@pytest.mark.parametrize('amount',['50','150','200'])
def test_partial_full_replacement_once(db_session,paid,amount):
    s,p,a=paid;original=raw(p);closed=raw(s)
    op=apply(db_session,s,p,**args(amount=amount));b=balances.summary(db_session,s)
    assert b['paid']==int(amount) and b['remaining']==200-int(amount)
    assert b['states'][p.id]=='replaced' and len(b['effective'])==1
    assert raw(p)==original and raw(s)==closed
    assert op.replacement_payout_id!=p.id
    assert a.iban not in json.dumps([op.before_state,op.after_state,op.impact])

@pytest.mark.parametrize('full',[False,True])
def test_void_partial_or_complete(db_session,paid,full):
    s,p,a=paid
    if full:
        op=apply(db_session,s,p,**args(amount='200'));p=db_session.get(OwnerPayout,op.replacement_payout_id)
    original=raw(p);op=apply(db_session,s,p,**args('void'));b=balances.summary(db_session,s)
    assert b['paid']==0 and b['remaining']==200 and b['available']==200
    assert raw(p)==original and s.status=='closed' and op.no_transfer
    assert not op.replacement_payout_id

def test_duplicate_one_real_record_preserved(db_session,paid):
    s,p,a=paid
    duplicate=service.payout(db_session,s.id,amount='100',effective_date=p.effective_date,bank_account_id=a.id,method='bank_transfer',request_key=str(uuid4()))
    apply(db_session,s,duplicate,**args('void'))
    assert balances.summary(db_session,s)['paid']==100
    assert balances.summary(db_session,s)['effective']==[p]

def test_history_date_reference_inactive_account(db_session,paid):
    s,p,a=paid;a.active=False;db_session.commit()
    first=apply(db_session,s,p,**args(amount='100',effective_date='2026-09-21',reference='CORRECTED'))
    nextp=db_session.get(OwnerPayout,first.replacement_payout_id)
    second=apply(db_session,s,nextp,**args(amount='90',effective_date='2026-09-21',reference='CORRECTED'))
    b=balances.summary(db_session,s)
    assert b['paid']==90 and len(b['operations'])==2
    assert nextp.account_snapshot==p.account_snapshot and second.original_payout_id==nextp.id
    assert not a.active

def test_limits_and_declarations(db_session,paid):
    s,p,a=paid
    for values in [args(amount='201'),args(amount='-1'),args('void',no_transfer=False),args(same_transfer=False),args(reason=''),args(effective_date='2099-01-01')]:
        with pytest.raises(ValueError):apply(db_session,s,p,**values)
    assert balances.summary(db_session,s)['paid']==100

def test_cross_owner_and_liquidation(db_session,paid,sample):
    s,p,a=paid;other=draft(db_session,sample,'b');service.close(db_session,other.id,other.fingerprint)
    with pytest.raises(LookupError):corrections.preview(db_session,other.id,p.id,**args())

def test_shared_owner_funds_and_stale(db_session,paid):
    s,p,a=paid;view=corrections.preview(db_session,s.id,p.id,**args(amount='150'))
    # Separate closed synthetic adjustment reduces this owner's available cash.
    snap=deepcopy(s.snapshot);snap['totals'].update(funds_balance='-80.00',prior_balance='0.00',payout_due='0.00',carry_forward='-80.00')
    other=OwnerSettlement(owner_id=s.owner_id,period_start=date(2026,10,1),period_end=date(2026,11,1),status='closed',closed_at=s.closed_at,selection=s.selection,fingerprint='synthetic',snapshot=snap,request_key=str(uuid4()))
    db_session.add(other);db_session.commit()
    with pytest.raises(ValueError,match='fondos'):apply(db_session,s,p,**args(amount='150'))
    assert balances.summary(db_session,s)['available']==20
    allowed=corrections.preview(db_session,s.id,p.id,**args(amount='110'))
    service.payout(db_session,s.id,amount='10',effective_date=p.effective_date,bank_account_id=a.id,method='bank_transfer',request_key=str(uuid4()))
    with pytest.raises(ValueError,match='cambiado'):corrections.confirm(db_session,s.id,p.id,**args(amount='110'),request_key=str(uuid4()),expected=allowed['fingerprint'],confirmed=True)

@pytest.mark.parametrize('kind',['void','replace'])
def test_concurrent_idempotence(db_session,paid,kind):
    s,p,a=paid;values=args(kind);v=corrections.preview(db_session,s.id,p.id,**values);key=str(uuid4());sid,pid=s.id,p.id;engine=db_session.get_bind();db_session.rollback()
    def run(k):
        with Session(engine) as db:
            return corrections.confirm(db,sid,pid,**values,request_key=k,expected=v['fingerprint'],confirmed=True).request_key
    with ThreadPoolExecutor(max_workers=2) as pool:assert list(pool.map(run,[key,key]))==[key,key]
    with pytest.raises(ValueError):run(str(uuid4()))
    db_session.expire_all();assert db_session.scalar(select(func.count()).select_from(Operation))==1
    assert db_session.scalar(select(func.count()).select_from(OwnerPayout))==(1 if kind=='void' else 2)

@pytest.mark.parametrize('kind',['void','replace'])
def test_complete_rollback(db_session,paid,kind):
    s,p,a=paid;before=raw(p)
    def fail(*_):raise RuntimeError('synthetic failure')
    event.listen(Operation,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError):apply(db_session,s,p,**args(kind))
    finally:event.remove(Operation,'before_insert',fail)
    db_session.expire_all();assert raw(p)==before
    assert db_session.scalar(select(func.count()).select_from(OwnerPayout))==1
    assert db_session.scalar(select(func.count()).select_from(Operation))==0

def test_closed_pdf_preserved(db_session,paid,tmp_path):
    from backend.services.settlement_document_service import SettlementDocumentService
    s,p,a=paid;docs=SettlementDocumentService(tmp_path/'docs');first=docs.generate(db_session,s.id)
    _,path=docs.download(db_session,s.id,first['version']);original=path.read_bytes();closed=deepcopy(s.snapshot)
    apply(db_session,s,p,**args(amount='50'))
    second=docs.generate(db_session,s.id)
    assert second['version']==first['version']+1 and path.read_bytes()==original and s.snapshot==closed
    from pypdf import PdfReader
    _,newpath=docs.download(db_session,s.id,second['version'])
    text=' '.join(p.extract_text() for p in PdfReader(newpath).pages)
    assert '150,00' in text

def test_pending_return_and_billing_block(db_session,paid,monkeypatch):
    s,p,a=paid
    monkeypatch.setattr(corrections.balances,'pending_returns',lambda *args:[1])
    with pytest.raises(ValueError,match='devoluciones'):apply(db_session,s,p,**args('void'))
    monkeypatch.setattr(corrections.balances,'pending_returns',lambda *args:[])
    s.selection=dict(s.selection,billing=True);db_session.commit()
    with pytest.raises(ValueError,match='compensaciones'):apply(db_session,s,p,**args())


def test_real_pending_refund_and_operator_privacy(db_session,paid,sample):
    from tests.unit.test_owner_settlement_service import refund
    s,p,a=paid
    values=args(reason='Revisar cuenta '+a.iban)
    v=corrections.preview(db_session,s.id,p.id,**values)
    op=corrections.confirm(db_session,s.id,p.id,**values,request_key=str(uuid4()),expected=v['fingerprint'],confirmed=True,operator_id='synthetic-operator-7')
    assert op.operator_id=='synthetic-operator-7'
    assert a.iban not in json.dumps([op.reason,op.before_state,op.after_state,op.impact])
    refund(db_session,sample)
    newp=db_session.get(OwnerPayout,op.replacement_payout_id)
    with pytest.raises(ValueError,match='devoluciones'):apply(db_session,s,newp,**args('void'))


def test_new_payout_after_void_respects_effective_balance(db_session,paid):
    s,p,a=paid;apply(db_session,s,p,**args('void'))
    new=service.payout(db_session,s.id,amount='200',effective_date=p.effective_date,bank_account_id=a.id,method='bank_transfer',request_key=str(uuid4()))
    assert balances.summary(db_session,s)['paid']==200 and balances.summary(db_session,s)['effective']==[new]
    with pytest.raises(ValueError):service.payout(db_session,s.id,amount='1',effective_date=p.effective_date,bank_account_id=a.id,method='bank_transfer',request_key=str(uuid4()))


def test_existing_compensation_guard_is_not_relaxed(db_session,paid):
    from backend.models.fee_billing import FeeCompensation,FeeObligation,FeeFund
    from backend.models.owner_settlement import OwnerSettlementLine
    s,p,a=paid;line=db_session.scalar(select(OwnerSettlementLine).where(OwnerSettlementLine.settlement_id==s.id))
    obligation=FeeObligation(owner_id=s.owner_id,settlement_id=s.id,source_line_id=line.id,source_key='synthetic-guard',kind='management_fee',effective_date=p.effective_date,amount=10,snapshot={})
    fund=FeeFund(owner_id=s.owner_id,settlement_id=s.id,source_line_id=line.id,effective_date=p.effective_date,amount=10)
    db_session.add_all([obligation,fund]);db_session.flush()
    db_session.add(FeeCompensation(obligation_id=obligation.id,fund_id=fund.id,settlement_id=s.id,effective_date=p.effective_date,amount=10,direction='application',request_key=str(uuid4())))
    db_session.commit()
    with pytest.raises(ValueError,match='compensaciones'):apply(db_session,s,p,**args('void'))
    assert balances.summary(db_session,s)['paid']==100
