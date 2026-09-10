from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
import re
from sqlalchemy import select

from backend.models.booking_charge import BookingCharge
from backend.models.payment import Payment
from backend.services.collection_plan_service import CollectionPlanService
from backend.services.financial_service import FinancialService
from backend.services.manual_payment_service import ManualPaymentService
from tests.integration.api.test_booking_finance_routes import make_finance_booking
from tests.integration.api.test_sepa_collections import scenario, count, COLLECTION
from tests.integration.api.test_manual_payments_and_returns import collect_all


def configured(db):
    booking = make_finance_booking(db)
    booking.check_in = date(2026, 7, 16)
    booking.check_out = date(2026, 12, 16)
    db.commit()
    finance = FinancialService()
    terms = finance.create_terms_draft(db, booking.id, booking.check_in, '400', deposit_agreed='400').data
    assert finance.confirm_terms(db, terms.id).success
    return booking, terms


def test_complete_plan_idempotent_no_future_payments_and_explicit_confirmation(client, db_session):
    booking, terms = configured(db_session)
    plan = CollectionPlanService()
    payload = dict(terms_id=terms.id, review_token=plan.review_token(booking, terms), include_deposit='true')
    response = client.post(f'/bookings/{booking.id}/finance/plan', data=payload)
    assert 'Confirme que ha revisado' in response.text
    assert count(db_session, BookingCharge) == 0
    payload['confirm_plan'] = 'yes'
    for _ in range(2):
        assert client.post(f'/bookings/{booking.id}/finance/plan', data=payload).status_code == 200
    rows = FinancialService().repository.list_charges(db_session, booking.id)
    assert len(rows) == 7 and all(c.lifecycle == 'posted' for c in rows)
    assert [c.amount for c in rows if c.type == 'rent'] == [Decimal('206.45'), *[Decimal('400')]*4, Decimal('193.55')]
    assert sum(c.amount for c in rows) == Decimal('2400')
    assert count(db_session, Payment) == 0


def test_changed_review_or_posted_never_silently_recalculated(db_session):
    booking, terms = configured(db_session)
    plan = CollectionPlanService()
    token = plan.review_token(booking, terms)
    booking.check_out = date(2026, 12, 17)
    db_session.commit()
    with pytest.raises(ValueError, match='calendario ha cambiado'):
        plan.generate(db_session, booking.id, terms.id, review_token=token)
    assert count(db_session, BookingCharge) == 0
    plan.generate(db_session, booking.id, terms.id, review_token=plan.review_token(booking, terms))
    before = [(c.id, c.amount, c.service_period_end) for c in FinancialService().repository.list_charges(db_session, booking.id)]
    booking.check_out = date(2026, 12, 18)
    db_session.commit()
    with pytest.raises(ValueError, match='no coinciden'):
        plan.generate(db_session, booking.id, terms.id, review_token=plan.review_token(booking, terms))
    assert before == [(c.id, c.amount, c.service_period_end) for c in FinancialService().repository.list_charges(db_session, booking.id)]


def test_plan_atomic_rollback(db_session, monkeypatch):
    booking, terms = configured(db_session)
    plan = CollectionPlanService()
    token = plan.review_token(booking, terms)
    original = db_session.add
    calls = 0
    def fail_second(value):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('simulated failure')
        original(value)
    monkeypatch.setattr(db_session, 'add', fail_second)
    with pytest.raises(RuntimeError):
        plan.generate(db_session, booking.id, terms.id, review_token=token)
    assert count(db_session, BookingCharge) == 0


def test_concurrent_plan_only_one_complete_calendar(db_session):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import Session
    booking, terms = configured(db_session)
    ids=(booking.id,terms.id)
    token=CollectionPlanService().review_token(booking,terms)
    engine=db_session.get_bind()
    db_session.rollback()
    def generate(_):
        with Session(engine,autoflush=False) as db:
            CollectionPlanService().generate(db,*ids,review_token=token,include_deposit=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(generate,range(2)))
    assert count(db_session,BookingCharge)==7 and count(db_session,Payment)==0


def test_matching_drafts_posted_stale_drafts_and_multiple_versions_blocked(db_session):
    booking,terms=configured(db_session)
    finance=FinancialService(); plan=CollectionPlanService()
    assert finance.generate_booking_charges(db_session,booking.id,terms.id).success
    rows=finance.repository.list_charges(db_session,booking.id)
    ids=[c.id for c in rows]
    plan.generate(db_session,booking.id,terms.id,review_token=plan.review_token(booking,terms))
    assert ids==[c.id for c in finance.repository.list_charges(db_session,booking.id)]
    assert all(c.lifecycle=='posted' for c in rows)
    new=finance.create_terms_draft(db_session,booking.id,date(2027,1,1),'450')
    assert new.success
    with pytest.raises(ValueError,match='múltiples versiones'):
        plan.generate(db_session,booking.id,terms.id,review_token=plan.review_token(booking,terms))


def test_stale_drafts_are_not_implicitly_replaced(db_session):
    booking,terms=configured(db_session)
    finance=FinancialService(); plan=CollectionPlanService()
    assert finance.generate_booking_charges(db_session,booking.id,terms.id).success
    original=[(c.id,c.amount) for c in finance.repository.list_charges(db_session,booking.id)]
    booking.check_out=date(2026,12,20);db_session.commit()
    with pytest.raises(ValueError,match='no coinciden'):
        plan.generate(db_session,booking.id,terms.id,review_token=plan.review_token(booking,terms))
    assert original==[(c.id,c.amount) for c in finance.repository.list_charges(db_session,booking.id)]
    assert all(c.lifecycle=='draft' for c in finance.repository.list_charges(db_session,booking.id))


def test_charge_payment_trace_summary_and_future(client, db_session, monkeypatch):
    today = date(2026, 9, 1)
    for module in ('backend.api.routers.booking_finance', 'backend.services.manual_payment_service', 'backend.services.financial_service'):
        monkeypatch.setattr(module+'.business_today', lambda: today)
    booking, terms = configured(db_session)
    plan = CollectionPlanService()
    plan.generate(db_session, booking.id, terms.id, review_token=plan.review_token(booking, terms))
    charges = FinancialService().repository.list_charges(db_session, booking.id)
    ManualPaymentService().register(db_session, booking.id, amount='406.45', effective_date=today,
        method='bank_transfer', request_key=str(uuid4()), allocations=[(charges[0].id,'206.45'),(charges[1].id,'200')])
    page = client.get(f'/bookings/{booking.id}/finance')
    assert page.status_code == 200
    def row(index):
        return re.search(r'<tr id="charge-'+str(charges[index].id)+r'".*?</tr>',page.text,re.S).group()
    assert '✓ Cobrado' in row(0)
    assert 'Parcial' in row(1) and '! Vencido' in row(1)
    assert 'Pendiente' in row(2)
    assert 'Previsto futuro' in row(3)
    assert 'Transferencia' in row(0) and '<details' in row(0)
    assert f'href="#charge-{charges[0].id}"' in page.text
    assert f'href="#charge-{charges[1].id}"' in page.text
    from backend.services.financial_account_view import account_view
    finance=FinancialService()
    balances={c.id:finance.charge_balance(db_session,c.id,today) for c in charges}
    view=account_view(db_session,charges,balances,ManualPaymentService().history(db_session,booking.id),today)
    assert view['planned']==2000 and view['future']==Decimal('993.55') and view['due_today']==400
    summary=finance.booking_summary(db_session,booking.id,today)
    assert summary.allocated_total==Decimal('406.45')
    assert summary.overdue_balance==200 and summary.outstanding_balance==Decimal('1593.55')


def test_return_visual_and_bidirectional_trace(client, db_session, scenario):
    batch, ids=collect_all(db_session,scenario)
    page=client.get(f'/collections/{batch.id}')
    assert '✓ Cobrado' in page.text and 'text-bg-success' in page.text
    assert 'Seleccionar todos los cobrados' not in page.text
    scenario[0].return_debits(db_session,batch.id,ids,COLLECTION,'Incidencia sintética')
    page=client.get(f'/collections/{batch.id}')
    assert '! Devuelto' in re.search(r'<tr class="table-danger">.*?</tr>',page.text,re.S).group()
    assert 'Cobrado 10/09/2026' in page.text and 'Devuelto 10/09/2026' in page.text
    finance=client.get(f'/bookings/{scenario[1].id}/finance')
    assert finance.status_code==200
    assert 'Devolución SEPA' in finance.text and 'Reabierto por devolución SEPA' in finance.text
    assert f'href="/collections/{batch.id}"' in finance.text
    assert 'Reembolso' not in finance.text
