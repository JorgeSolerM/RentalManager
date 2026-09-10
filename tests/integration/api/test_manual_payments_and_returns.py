from datetime import timedelta
from decimal import Decimal
from uuid import uuid4
import pytest
from sqlalchemy import select
from backend.models.payment import Payment
from backend.models.payment_allocation import PaymentAllocation
from backend.models.sepa_collection import SepaDebit, SepaDebitChargeAllocation
from backend.services.manual_payment_service import ManualPaymentService
from tests.integration.api.test_sepa_collections import scenario, create, count, add_second_booking, COLLECTION


@pytest.fixture
def manual(monkeypatch):
    monkeypatch.setattr('backend.services.manual_payment_service.business_today',lambda:COLLECTION)
    return ManualPaymentService()


def pay(db, scenario, manual, amount='400', **kwargs):
    charge=scenario[4][0]
    return manual.register(db,scenario[1].id,amount=amount,effective_date=COLLECTION,
        method=kwargs.pop('method','cash'),allocations=kwargs.pop('allocations',[(charge.id,amount)]),
        request_key=kwargs.pop('request_key',str(uuid4())),**kwargs)


@pytest.mark.parametrize('method',['cash','bank_transfer','other'])
def test_manual_payment_without_debit(db_session,scenario,manual,method):
    p=pay(db_session,scenario,manual,method=method)
    assert p.method==method and p.lifecycle=='posted'
    assert count(db_session,SepaDebit)==0
    assert scenario[0].finance.charge_balance(db_session,scenario[4][0].id).payment_status=='paid'


def test_partial_multi_charge_proposal_and_unapplied(db_session,scenario,manual):
    rows,left=manual.propose(db_session,scenario[1].id,'450')
    assert [r[2] for r in rows]==[Decimal('400'),Decimal('50'),Decimal('0')]
    assert left==0
    p=pay(db_session,scenario,manual,'450',allocations=[(rows[0][0].id,'400'),(rows[1][0].id,'50')])
    assert count(db_session,PaymentAllocation)==2
    assert scenario[0].finance.charge_balance(db_session,rows[1][0].id).outstanding_amount==350
    pay(db_session,scenario,manual,'10',allocations=[],allow_unallocated=True)
    assert manual.finance.booking_summary(db_session,scenario[1].id).unapplied_balance==10


def test_manual_idempotency_and_validation(db_session,scenario,manual):
    key=str(uuid4())
    p=pay(db_session,scenario,manual,'100',request_key=key)
    assert pay(db_session,scenario,manual,'100',request_key=key).id==p.id
    assert count(db_session,Payment)==1
    with pytest.raises(ValueError): pay(db_session,scenario,manual,'101',request_key=key)
    with pytest.raises(ValueError): pay(db_session,scenario,manual,'301')
    with pytest.raises(ValueError): pay(db_session,scenario,manual,'100',allocations=[])
    with pytest.raises(ValueError): pay(db_session,scenario,manual,'10',method='sepa_direct_debit')
    assert count(db_session,Payment)==1


@pytest.mark.parametrize('exported',[False,True])
def test_paid_elsewhere_cancel_keeps_history(db_session,scenario,manual,exported):
    service=scenario[0]
    batch=create(db_session,scenario)
    if exported: service.export(db_session,batch.id)
    debit=db_session.scalar(select(SepaDebit))
    pay(db_session,scenario,manual,'825.30',allocations=[(c.id,str(c.amount)) for c in scenario[4]])
    assert service.balance_warning(db_session,debit)
    service.cancel(db_session,batch.id,[debit.id])
    assert debit.status=='cancelled' and debit.cancellation_reason=='Pagado por otro medio'
    assert batch.status=='cancelled' and count(db_session,SepaDebit)==1
    assert all(not a.reserved for a in debit.allocations)
    with pytest.raises(ValueError): service.present(db_session,batch.id)
    with pytest.raises(ValueError): service.export(db_session,batch.id)
    assert count(db_session,Payment)==1


def test_presented_manual_payment_warns_and_blocks_collection(db_session,scenario,manual):
    service=scenario[0]; batch=create(db_session,scenario)
    service.export(db_session,batch.id);service.present(db_session,batch.id)
    debit=db_session.scalar(select(SepaDebit))
    pay(db_session,scenario,manual,'100')
    assert 'todavía puede' in service.balance_warning(db_session,debit)
    assert debit.status=='presented'
    with pytest.raises(ValueError,match='otro medio'): service.collect(db_session,batch.id,[debit.id],COLLECTION)
    with pytest.raises(ValueError): service.cancel(db_session,batch.id,[debit.id])
    assert count(db_session,Payment)==1


def test_manual_payment_after_export_blocks_presentation(db_session,scenario,manual):
    service=scenario[0];batch=create(db_session,scenario);service.export(db_session,batch.id)
    pay(db_session,scenario,manual,'100')
    with pytest.raises(ValueError): service.present(db_session,batch.id)
    assert service.get_batch(db_session,batch.id).status=='exported'


def collect_all(db,scenario):
    service=scenario[0];batch=create(db,scenario)
    service.export(db,batch.id);service.present(db,batch.id)
    ids=[d.id for g in service.get_batch(db,batch.id).groups for d in g.debits]
    service.collect(db,batch.id,ids,COLLECTION)
    return batch,ids


def test_return_preserves_receipt_reopens_charges_and_is_idempotent(db_session,scenario):
    service=scenario[0];batch,ids=collect_all(db_session,scenario)
    debit=db_session.get(SepaDebit,ids[0]); original=debit.payment_id
    original_allocations=[(a.id,a.charge_id,a.amount) for a in db_session.scalars(select(PaymentAllocation))]
    service.return_debits(db_session,batch.id,ids,COLLECTION,'Devolución real','Referencia sintética')
    assert debit.status=='returned' and debit.payment_id==original
    assert db_session.get(Payment,original).lifecycle=='posted'
    reversal=db_session.get(Payment,debit.return_payment_id)
    assert reversal.direction=='refund' and reversal.corrects_payment_id==original
    assert [(a.id,a.charge_id,a.amount) for a in db_session.scalars(select(PaymentAllocation).where(PaymentAllocation.payment_id==original))]==original_allocations
    assert all(service.finance.charge_balance(db_session,c.id).outstanding_amount==c.amount for c in scenario[4])
    assert not any(a.reserved for a in debit.allocations)
    service.return_debits(db_session,batch.id,ids,COLLECTION)
    assert count(db_session,Payment)==2
    with pytest.raises(ValueError):service.collect(db_session,batch.id,ids,COLLECTION)
    assert not service.finance.void_payment(db_session,original).success
    assert not service.finance.void_payment(db_session,reversal.id).success


def test_partial_batch_return_aggregate(db_session,scenario):
    service,booking,_,_,charges=scenario
    _,extra=add_second_booking(db_session,scenario)
    batch=service.create(db_session,COLLECTION.replace(day=1),[booking.room.property_id],COLLECTION,[c.id for c in charges]+[extra.id],str(uuid4()))
    service.export(db_session,batch.id); service.present(db_session,batch.id)
    ids=[d.id for g in service.get_batch(db_session,batch.id).groups for d in g.debits]
    service.collect(db_session,batch.id,ids[:1],COLLECTION)
    service.return_debits(db_session,batch.id,ids[:1],COLLECTION)
    assert service.batch_label(service.get_batch(db_session,batch.id))=='Parcialmente cobrada con devoluciones'
    service.collect(db_session,batch.id,ids[1:],COLLECTION)
    assert service.batch_label(service.get_batch(db_session,batch.id))=='Cobrada con devoluciones'


def test_returns_rollback_and_dates(db_session,scenario,monkeypatch):
    service=scenario[0];batch,ids=collect_all(db_session,scenario)
    with pytest.raises(ValueError):service.return_debits(db_session,batch.id,ids,COLLECTION-timedelta(days=1))
    with pytest.raises(ValueError):service.return_debits(db_session,batch.id,ids,COLLECTION+timedelta(days=1))
    original=db_session.add
    def fail(obj,*args,**kwargs):
        if isinstance(obj,PaymentAllocation):raise RuntimeError('synthetic failure')
        return original(obj,*args,**kwargs)
    monkeypatch.setattr(db_session,'add',fail)
    with pytest.raises(RuntimeError):service.return_debits(db_session,batch.id,ids,COLLECTION)
    assert count(db_session,Payment)==1
    assert db_session.get(SepaDebit,ids[0]).status=='collected'


def test_manual_rollback(db_session,scenario,manual,monkeypatch):
    original=db_session.add
    def fail(obj,*args,**kwargs):
        if isinstance(obj,PaymentAllocation):raise RuntimeError('synthetic failure')
        return original(obj,*args,**kwargs)
    monkeypatch.setattr(db_session,'add',fail)
    with pytest.raises(RuntimeError):pay(db_session,scenario,manual)
    assert count(db_session,Payment)==0


def test_payment_routes_review_and_history(client,db_session,scenario,manual,monkeypatch):
    monkeypatch.setattr('backend.api.routers.booking_finance.business_today',lambda:COLLECTION)
    bid=scenario[1].id
    assert 'Registrar pago' in client.get(f'/bookings/{bid}/finance').text
    data={'amount':'100','effective_date':str(COLLECTION),'method':'cash'}
    response=client.post(f'/bookings/{bid}/finance/payments/preview',data=data)
    assert response.status_code==200 and 'Revisar aplicación' in response.text
    assert count(db_session,Payment)==0
    data.update(request_key=str(uuid4()),**{f'allocation_{scenario[4][0].id}':'100'})
    response=client.post(f'/bookings/{bid}/finance/payments/register',data=data)
    assert response.status_code==200 and 'Pago en efectivo' in response.text and '100.00' in response.text
    assert 'Pagos y devoluciones' in response.text
    assert client.post(f'/bookings/{bid}/finance/payments/register',data={'amount':'broken'}).status_code==400


def test_return_route_and_public_privacy(client,db_session,scenario):
    batch,ids=collect_all(db_session,scenario)
    response=client.post(f'/collections/{batch.id}/return',data={'debit_ids':ids,'returned_on':str(COLLECTION)})
    assert response.status_code==200 and 'Devuelto' in response.text
    assert 'Cobrado 10/09/2026' in response.text and 'Devuelto 10/09/2026' in response.text
    assert scenario[3].debtor_iban not in response.text
    from fastapi.testclient import TestClient
    from backend.public_main import app
    with TestClient(app) as public:
        assert public.get(f'/bookings/{scenario[1].id}/finance/payments/new').status_code==404


def test_concurrent_manual_registration_only_one_receipt(db_session,scenario,manual):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import Session
    key=str(uuid4()); booking_id=scenario[1].id; charge_id=scenario[4][0].id
    engine=db_session.get_bind()
    db_session.rollback()
    def register():
        with Session(engine,autoflush=False) as db:
            return manual.register(db,booking_id,amount='400',effective_date=COLLECTION,
                method='cash',allocations=[(charge_id,'400')],request_key=key).id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids=list(pool.map(lambda _:register(),range(2)))
    assert ids[0]==ids[1]
    assert count(db_session,Payment)==1


def test_concurrent_returns_only_one_compensation(db_session,scenario):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import Session
    service=scenario[0];batch,ids=collect_all(db_session,scenario)
    batch_id=batch.id; engine=db_session.get_bind(); db_session.rollback()
    def reverse():
        with Session(engine,autoflush=False) as db:
            return service.return_debits(db,batch_id,ids,COLLECTION).id
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _:reverse(),range(2)))==[batch_id,batch_id]
    assert count(db_session,Payment)==2


def test_exclude_before_export_and_cancel_export_does_not_rewrite_file(db_session,scenario):
    service,booking,_,_,charges=scenario
    other,charge=add_second_booking(db_session,scenario,other_creditor=True)
    batch=service.create(db_session,COLLECTION.replace(day=1),[booking.room.property_id,other.room.property_id],COLLECTION,[c.id for c in charges]+[charge.id],str(uuid4()))
    first=service.get_batch(db_session,batch.id).groups[0].debits[0]
    service.cancel(db_session,batch.id,[first.id])
    service.export(db_session,batch.id)
    # Re-export remains idempotent even with an entirely excluded creditor group.
    service.export(db_session,batch.id)
    second=service.get_batch(db_session,batch.id).groups[1].debits[0]
    artifact=second.group.artifact
    content=service.artifact_path(db_session,artifact.id).read_bytes()
    service.cancel(db_session,batch.id,[second.id])
    assert service.artifact_path(db_session,artifact.id).read_bytes()==content
    assert batch.status=='cancelled'


def test_return_then_explicit_new_batch_uses_new_instruction(db_session,scenario):
    service=scenario[0];batch,ids=collect_all(db_session,scenario)
    original=db_session.get(SepaDebit,ids[0]); original_reference=original.end_to_end_id
    service.return_debits(db_session,batch.id,ids,COLLECTION)
    new=create(db_session,scenario)
    debit=service.get_batch(db_session,new.id).groups[0].debits[0]
    assert debit.retry_of_id==ids[0] and debit.end_to_end_id!=original_reference
    assert db_session.get(SepaDebit,ids[0]).status=='returned'


def test_multi_return_rollback_after_first_was_processed(db_session,scenario,monkeypatch):
    service,booking,_,_,charges=scenario
    _,charge=add_second_booking(db_session,scenario)
    batch=service.create(db_session,COLLECTION.replace(day=1),[booking.room.property_id],COLLECTION,[c.id for c in charges]+[charge.id],str(uuid4()))
    service.export(db_session,batch.id);service.present(db_session,batch.id)
    ids=[d.id for g in service.get_batch(db_session,batch.id).groups for d in g.debits]
    service.collect(db_session,batch.id,ids,COLLECTION)
    original=db_session.add
    def fail(obj,*args,**kwargs):
        if isinstance(obj,Payment) and obj.direction=='refund' and obj.booking_id!=booking.id:
            raise RuntimeError('synthetic second-debit failure')
        return original(obj,*args,**kwargs)
    monkeypatch.setattr(db_session,'add',fail)
    with pytest.raises(RuntimeError):service.return_debits(db_session,batch.id,ids,COLLECTION)
    assert count(db_session,Payment)==2
    assert all(db_session.get(SepaDebit,i).status=='collected' for i in ids)
