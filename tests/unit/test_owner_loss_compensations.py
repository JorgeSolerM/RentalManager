from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import pytest
from sqlalchemy import select, func, event
from sqlalchemy.orm import Session
from backend.models.owner_loss_compensation import OwnerLossCompensationAuthorization as Authorization, OwnerLossCompensationApplication as Application
from backend.models.owner_settlement import OwnerPayout, OwnerSettlementLine
from backend.services.owner_loss_compensation_service import OwnerLossCompensationService
from tests.unit.test_owner_transfer_losses import sample, paid, register, recognize, balances, raw, extra, draft, service, recover, pay, recoveries, inputs

compensations = OwnerLossCompensationService()

def owner_loss(db, s, i, amount='100', **changes):
    return recognize(db, i, amount=amount, responsible='owner', responsible_owner_id=s.owner_id,
                     agreement='Acuerdo sintético expreso', authorized=True, **changes)

def authorization_values(s, loss, **changes):
    v=dict(mode='authorize',loss_id=loss.id,amount=str(loss.amount),agreement_reference=f'SYNTHETIC-AGREEMENT-{loss.id}',
           settlement_ids=[s.id],authorized=True,reason='Autoriza descuento',evidence='Documento sintético firmado')
    v.update(changes);return v

def application_values(s, a, **changes):
    v=dict(mode='apply',authorization_id=a.id,settlement_id=s.id,amount='40',reason='Aplicación acordada',evidence='Apartado sintético')
    v.update(changes);return v

def confirm(db, i, v, **kw):
    preview=compensations.preview(db,i.id,**v)
    return compensations.confirm(db,i.id,**v,request_key=kw.get('request_key',str(uuid4())),expected=preview['fingerprint'],confirmed=True)

def setup(db,s,p,**changes):
    i=register(db,s,p,**changes);loss=owner_loss(db,s,i);a=confirm(db,i,authorization_values(s,loss));return i,loss,a

@pytest.mark.parametrize('amount',['40','100'])
def test_partial_successive_no_fictitious_cash(db_session,paid,amount):
    s,p,bank=paid;i,loss,a=setup(db_session,s,p);before=balances.summary(db_session,s);original=raw(s);oldp=raw(p)
    operation=confirm(db_session,i,application_values(s,a,amount=amount));b=balances.summary(db_session,s)
    assert Decimal(operation.before_state['applied'])==0 and Decimal(operation.after_state['applied'])==Decimal(amount)
    assert Decimal(operation.after_state['available_authorization'])==a.amount-Decimal(amount)
    assert operation.before_state['available']==operation.after_state['available']
    assert b['remaining']==before['remaining']-Decimal(amount) and b['compensated']==Decimal(amount)
    for k in ('paid','available','deficit','cash_used','pending_recovery'):assert b[k]==before[k]
    assert raw(s)==original and raw(p)==oldp and db_session.scalar(select(func.count()).select_from(OwnerPayout))==1
    if amount=='40':
        confirm(db_session,i,application_values(s,a,amount='60'))
        assert balances.summary(db_session,s)['compensated']==100
    with pytest.raises(ValueError):confirm(db_session,i,application_values(s,a,amount='0.01'))

def test_total_and_mixed_status(db_session,paid):
    s,p,bank=paid;i=register(db_session,s,p,**extra(s,p,amount='200',allocations={str(s.owner_id):'200'}));loss=owner_loss(db_session,s,i,amount='200');a=confirm(db_session,i,authorization_values(s,loss))
    confirm(db_session,i,application_values(s,a,amount='100'));b=balances.summary(db_session,s)
    assert b['remaining']==0 and b['paid']==100 and b['status']=='Pagado y compensado'
    assert b['deficit']==100 and b['available']==0
    with pytest.raises(ValueError):confirm(db_session,i,application_values(s,a,amount='1'))

def test_fully_compensated_without_payment(db_session,paid):
    s,p,bank=paid;i,loss,a=setup(db_session,s,p)
    confirm(db_session,i,application_values(s,a,amount='100'))
    second=register(db_session,s,p,**extra(s,p,amount='100',allocations={str(s.owner_id):'100'}))
    loss2=owner_loss(db_session,s,second);a2=confirm(db_session,second,authorization_values(s,loss2))
    confirm(db_session,second,application_values(s,a2,amount='100'))
    b=balances.summary(db_session,s)
    assert b['remaining']==0 and b['paid']==0 and b['compensated']==200 and b['status']=='Compensado' and b['available']==0

def test_pending_responsibility_assigned_then_authorized(db_session,paid):
    from tests.unit.test_owner_transfer_losses import losses,values
    s,p,bank=paid;i=register(db_session,s,p);loss=recognize(db_session,i,amount='100')
    with pytest.raises(ValueError):confirm(db_session,i,authorization_values(s,loss))
    v=values(kind='responsibility',loss_id=loss.id,amount='100',responsible='owner',responsible_owner_id=s.owner_id,agreement='Specific',authorized=True)
    pr=losses.preview(db_session,i.id,**v);r=losses.confirm(db_session,i.id,**v,request_key=str(uuid4()),expected=pr['fingerprint'],confirmed=True)
    a=confirm(db_session,i,authorization_values(s,loss));assert a.responsibility_id==r.id

def test_duplicate_authorization_different_keys_and_refs(db_session,paid):
    s,p,bank=paid;i,loss,a=setup(db_session,s,p)
    with pytest.raises(ValueError):confirm(db_session,i,authorization_values(s,loss,agreement_reference='CHANGED'))
    with pytest.raises(ValueError):compensations.preview(db_session,i.id,**authorization_values(s,loss,amount='101'))

def test_global_agreement_not_reused(db_session,paid):
    s,p,bank=paid;i=register(db_session,s,p);l1=owner_loss(db_session,s,i,amount='40');l2=owner_loss(db_session,s,i,amount='60',evidence_reference='SECOND')
    confirm(db_session,i,authorization_values(s,l1,agreement_reference='Global Agreement'))
    with pytest.raises(ValueError):confirm(db_session,i,authorization_values(s,l2,agreement_reference='  GLOBAL  agreement '))

def test_owner_agreement_and_scope_required(db_session,paid,sample):
    s,p,bank=paid;i=register(db_session,s,p);loss=owner_loss(db_session,s,i);other=draft(db_session,sample,'b');service.close(db_session,other.id,other.fingerprint)
    for changes in [dict(authorized=False),dict(agreement_reference=''),dict(settlement_ids=[]),dict(settlement_ids=[other.id])]:
        with pytest.raises(ValueError):compensations.preview(db_session,i.id,**authorization_values(s,loss,**changes))
    a=confirm(db_session,i,authorization_values(s,loss))
    with pytest.raises(ValueError):confirm(db_session,i,application_values(other,a))

def test_coprop_responsibility_only_affects_correct_owner(db_session,paid,sample):
    s,p,bank=paid;other=draft(db_session,sample,'b');service.close(db_session,other.id,other.fingerprint)
    i=register(db_session,s,p,**extra(s,p,allocations={str(s.owner_id):'40',str(other.owner_id):'40'}))
    loss=owner_loss(db_session,other,i,amount='40');a=confirm(db_session,i,authorization_values(other,loss));before=balances.summary(db_session,s)
    confirm(db_session,i,application_values(other,a));after=balances.summary(db_session,s)
    for k in ('paid','remaining','available','deficit'):assert before[k]==after[k]
    assert balances.summary(db_session,other)['compensated']==40

def test_deficit_not_cured(db_session,paid):
    s,p,bank=paid;i,loss,a=setup(db_session,s,p,**extra(s,p,amount='300',allocations={str(s.owner_id):'300'}))
    confirm(db_session,i,application_values(s,a));b=balances.summary(db_session,s)
    assert b['deficit']==200 and b['available']==0 and b['remaining']==60

def test_unknown_funds_block(db_session,paid):
    s,p,bank=paid;i,loss,a=setup(db_session,s,p)
    register(db_session,s,p,**extra(s,p,allocations={},bank_transaction_id='UNKNOWN-EXTRA'))
    with pytest.raises(ValueError):confirm(db_session,i,application_values(s,a))

def test_prior_recovery_and_later_recovery_blocks_dispositions(db_session,paid):
    s,p,bank=paid;i=register(db_session,s,p);recover(db_session,i,bank,amount='20');loss=owner_loss(db_session,s,i,amount='80');a=confirm(db_session,i,authorization_values(s,loss))
    op=confirm(db_session,i,application_values(s,a));before=raw(op);remaining=balances.summary(db_session,s)['remaining']
    preview=recoveries.preview(db_session,i.id,**inputs(bank,amount='10',bank_transaction_id='AFTER-COMPENSATION'))
    assert Decimal(preview['impact']['funds'][str(s.owner_id)]['available_after'])==0
    recover(db_session,i,bank,amount='10',bank_transaction_id='AFTER-COMPENSATION')
    b=balances.summary(db_session,s)
    assert b['remaining']==remaining and b['available']==0 and b['recovered_funds']==30 and raw(op)==before
    assert any('Regularización posterior pendiente' in x for x in b['payout_blockers'])
    with pytest.raises(ValueError):confirm(db_session,i,application_values(s,a,amount='10'))
    with pytest.raises(ValueError):pay(db_session,s,bank,amount='10')
    recover(db_session,i,bank,amount='15',bank_transaction_id='SECOND-AFTER-COMPENSATION')
    assert balances.summary(db_session,s)['recovered_funds']==45

def test_idempotence_stale_and_rollback(db_session,paid):
    s,p,bank=paid;i,loss,a=setup(db_session,s,p);v=application_values(s,a);pr=compensations.preview(db_session,i.id,**v);key=str(uuid4())
    ids=[compensations.confirm(db_session,i.id,**v,request_key=key,expected=pr['fingerprint'],confirmed=True).id for _ in range(2)]
    assert ids[0]==ids[1]
    with pytest.raises(ValueError):compensations.confirm(db_session,i.id,**v,request_key=str(uuid4()),expected=pr['fingerprint'],confirmed=True)
    v=application_values(s,a,amount='20');pr=compensations.preview(db_session,i.id,**v)
    def fail(*args):raise RuntimeError('Synthetic rollback')
    event.listen(Application,'after_insert',fail)
    try:
        with pytest.raises(RuntimeError):compensations.confirm(db_session,i.id,**v,request_key=str(uuid4()),expected=pr['fingerprint'],confirmed=True)
    finally:event.remove(Application,'after_insert',fail)
    assert db_session.scalar(select(func.count()).select_from(Application))==1

@pytest.mark.parametrize('same_key',[True,False])
def test_concurrent_applications(db_session,paid,same_key):
    s,p,bank=paid;i,loss,a=setup(db_session,s,p);iid=i.id;v=application_values(s,a,amount='80');pr=compensations.preview(db_session,iid,**v);key=str(uuid4());engine=db_session.get_bind();db_session.rollback()
    def run(k):
        with Session(engine) as db:
            try:return compensations.confirm(db,iid,**v,request_key=k,expected=pr['fingerprint'],confirmed=True).id
            except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:r=list(pool.map(run,[key,key if same_key else str(uuid4())]))
    assert r[0]==r[1] if same_key else r.count(None)==1
    assert db_session.scalar(select(func.count()).select_from(Application))==1

@pytest.mark.parametrize('other',['recovery','payout'])
def test_concurrent_compensation_and_cash(db_session,paid,other):
    from tests.unit.test_owner_transfer_recoveries import reviewed,payinputs
    s,p,bank=paid;i,loss,a=setup(db_session,s,p);iid=i.id;sid=s.id
    v=application_values(s,a);pr=compensations.preview(db_session,iid,**v)
    sv=recoveries if other=='recovery' else reviewed;target=iid if other=='recovery' else sid
    cv=inputs(bank) if other=='recovery' else payinputs(bank);cp=sv.preview(db_session,target,**cv);engine=db_session.get_bind();db_session.rollback()
    def run(which):
        with Session(engine) as db:
            try:
                if which:sv.confirm(db,target,**cv,request_key=str(uuid4()),expected=cp['fingerprint'],confirmed=True)
                else:compensations.confirm(db,iid,**v,request_key=str(uuid4()),expected=pr['fingerprint'],confirmed=True)
                return True
            except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(run,[False,True]))==1

def test_pdf_history_and_future_informative_not_double_discount(db_session,paid,sample,tmp_path):
    from backend.services.settlement_document_service import SettlementDocumentService
    from backend.services.owner_loss_compensation_state import document_compensations
    s,p,bank=paid;i,loss,a=setup(db_session,s,p);docs=SettlementDocumentService(tmp_path/'docs')
    first=docs.generate(db_session,s.id);_,path=docs.download(db_session,s.id,first['version']);original=path.read_bytes();closed=raw(s)
    confirm(db_session,i,application_values(s,a));second=docs.generate(db_session,s.id)
    assert second['version']>first['version'] and path.read_bytes()==original and raw(s)==closed
    # A later closed statement may cite this application but has no consumption of its own.
    from copy import deepcopy
    from backend.models.owner_settlement import OwnerSettlement
    from datetime import datetime,timedelta
    future=OwnerSettlement(owner_id=s.owner_id,period_start=s.period_start,period_end=s.period_end,status='closed',selection=deepcopy(s.selection),snapshot=deepcopy(s.snapshot),fingerprint='future',request_key=str(uuid4()),closed_at=datetime.now()+timedelta(seconds=2))
    db_session.add(future);db_session.commit()
    assert all(x['informative'] for x in document_compensations(db_session,future))
    assert balances.summary(db_session,future)['compensated']==0 and balances.summary(db_session,future)['remaining']==Decimal(future.snapshot['totals']['payout_due'])


def test_owner_projection_is_scoped_and_incident_form_keeps_other_owner(db_session, paid, sample):
    from backend.services.owner_loss_compensation_state import compensation_state
    s, p, bank = paid
    other = draft(db_session, sample, 'b')
    service.close(db_session, other.id, other.fingerprint)
    before = compensation_state(db_session, s.owner_id, s.id)
    i = register(db_session, s, p, **extra(s, p, allocations={str(s.owner_id): '40', str(other.owner_id): '40'}))
    loss = owner_loss(db_session, other, i, amount='40')
    a = confirm(db_session, i, authorization_values(other, loss))
    confirm(db_session, i, application_values(other, a))
    statements = []
    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(db_session.bind, 'before_cursor_execute', capture)
    try:
        after = compensation_state(db_session, s.owner_id, s.id)
    finally:
        event.remove(db_session.bind, 'before_cursor_execute', capture)
    assert after['fingerprint_state'] == before['fingerprint_state'] == []
    assert after['compensated'] == 0 and not after['applications']
    for table in ('owner_loss_compensation_authorizations', 'owner_loss_compensation_applications', 'owner_transfer_recoveries'):
        reads = [sql for sql in statements if 'FROM ' + table in sql]
        assert reads and all('WHERE' in sql for sql in reads)
    view = compensations.form(db_session, i.id)
    assert [item.id for item in view['authorizations']] == [a.id]
    assert view['used'][a.id] == 40
    statements.clear()
    event.listen(db_session.bind, 'before_cursor_execute', capture)
    try:
        assert balances.summary(db_session, other)['compensated'] == 40
    finally:
        event.remove(db_session.bind, 'before_cursor_execute', capture)
    for table in ('owner_loss_compensation_authorizations', 'owner_loss_compensation_applications'):
        assert sum('FROM ' + table in sql for sql in statements) == 1


def test_authorization_alone_preserves_obligation_cash_and_closed_history(db_session, paid):
    from backend.models.owner_settlement import Expense
    from backend.models.owner_transfer_recovery import OwnerTransferRecovery
    s, p, bank = paid
    i = register(db_session, s, p)
    loss = owner_loss(db_session, s, i)
    before = balances.summary(db_session, s)
    closed = raw(s)
    models = (OwnerPayout, Expense, OwnerTransferRecovery, OwnerSettlementLine)
    counts = [db_session.scalar(select(func.count()).select_from(model)) for model in models]
    confirm(db_session, i, authorization_values(s, loss))
    after = balances.summary(db_session, s)
    for key in ('remaining', 'paid', 'available', 'deficit', 'compensated', 'cash_used'):
        assert after[key] == before[key]
    assert raw(s) == closed
    assert counts == [db_session.scalar(select(func.count()).select_from(model)) for model in models]
    assert db_session.scalar(select(func.count()).select_from(Application)) == 0
