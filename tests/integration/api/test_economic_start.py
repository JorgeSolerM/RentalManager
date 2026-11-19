from datetime import date
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from backend.models.booking_charge import BookingCharge
from backend.models.payment import Payment
from backend.services.economic_start_service import EconomicStartService
from backend.services.financial_service import FinancialService
from backend.services.collection_plan_service import CollectionPlanService
from tests.integration.api.test_booking_finance_routes import make_finance_booking

service = EconomicStartService()
finance = FinancialService()


@pytest.fixture
def sample(db_session):
    b = make_finance_booking(db_session)
    b.check_in = date(2026, 9, 15); b.check_out = date(2027, 2, 15); db_session.commit()
    t = finance.create_terms_draft(db_session, b.id, b.check_in, '400', deposit_agreed='400').data
    assert finance.confirm_terms(db_session, t.id).success
    return b, t


def save(db, b, start=date(2026,12,1), **kwargs):
    view = service.preview(db, b.id, start)
    return service.confirm(db, b.id, start, view['fingerprint'], confirmed=True, **kwargs)


def test_old_booking_excludes_months_without_changing_identity(db_session, sample):
    b,t = sample
    before=(b.check_in,b.check_out,b.source_guest_name,b.room_id)
    view=service.preview(db_session,b.id,date(2026,12,1))
    assert len(view['included'])==3 and len(view['excluded'])==3
    assert view['total']==Decimal('1000') # February 1–14: 14/28.
    assert view['deposit_excluded']
    save(db_session,b)
    assert b.economic_management_start_configured_at is not None
    assert before==(b.check_in,b.check_out,b.source_guest_name,b.room_id)
    assert db_session.scalar(select(func.count()).select_from(BookingCharge))==0
    assert db_session.scalar(select(func.count()).select_from(Payment))==0
    rows=finance.preview_for_booking(b,t,include_deposit=True)
    assert [r.amount for r in rows]==[Decimal('400'),Decimal('400'),Decimal('200')]


def test_entry_month_keeps_original_proration_and_deposit(db_session,sample):
    b,t=sample;original=finance.preview_for_booking(b,t,include_deposit=True)
    save(db_session,b,date(2026,9,1))
    assert finance.preview_for_booking(b,t,include_deposit=True)==original


@pytest.mark.parametrize('start',[date(2026,12,2),date(2026,8,1),date(2027,3,1)])
def test_invalid_month(db_session,sample,start):
    with pytest.raises(ValueError):service.preview(db_session,sample[0].id,start)


def test_auto_drafts_require_explicit_removal_and_keep_keys(db_session,sample):
    b,t=sample
    assert finance.generate_booking_charges(db_session,b.id,t.id,include_deposit=True).success
    keys={c.generation_key for c in finance.repository.list_charges(db_session,b.id) if c.service_period_start and c.service_period_start>=date(2026,12,1)}
    with pytest.raises(ValueError,match='retirada'):save(db_session,b)
    save(db_session,b,replace_drafts=True)
    assert {c.generation_key for c in finance.repository.list_charges(db_session,b.id)}==keys
    plan=CollectionPlanService();token=plan.review_token(b,t)
    plan.generate(db_session,b.id,t.id,review_token=token,include_deposit=True)
    plan.generate(db_session,b.id,t.id,review_token=token,include_deposit=True)
    assert db_session.scalar(select(func.count()).select_from(BookingCharge))==3
    assert all(c.lifecycle=='posted' for c in finance.repository.list_charges(db_session,b.id))


def test_manual_draft_affected_blocks(db_session,sample):
    b,t=sample
    assert finance.create_charge(db_session,b.id,'utilities','Manual',date(2026,10,1),'20').success
    assert service.preview(db_session,b.id,date(2026,12,1))['blockers']
    with pytest.raises(ValueError):save(db_session,b)
    assert b.economic_management_start is None


@pytest.mark.parametrize('history',['posted','void','payment'])
def test_history_blocks(db_session,sample,history):
    b,t=sample
    if history=='payment':
        assert finance.create_payment(db_session,b.id,date(2026,10,1),'20','receipt','cash').success
    else:
        c=finance.create_charge(db_session,b.id,'rent','History',date(2026,10,1),'20').data
        assert finance.post_charge(db_session,c.id).success
        if history=='void':assert finance.void_charge(db_session,c.id,'Correction').success
    with pytest.raises(ValueError):save(db_session,b)


def test_stale_review_and_missing_confirmation(db_session,sample):
    b,t=sample;view=service.preview(db_session,b.id,date(2026,12,1))
    with pytest.raises(ValueError,match='Confirme'):service.confirm(db_session,b.id,view['start'],view['fingerprint'])
    b.check_out=date(2027,2,14);db_session.commit()
    with pytest.raises(ValueError,match='cambiado'):service.confirm(db_session,b.id,view['start'],view['fingerprint'],confirmed=True)


def test_concurrent_confirmation_idempotent(db_session,sample):
    b,t=sample;bid=b.id;view=service.preview(db_session,bid,date(2026,12,1))
    def run(_):
        with Session(db_session.bind) as db:
            return service.confirm(db,bid,view['start'],view['fingerprint'],confirmed=True).economic_management_start_configured_at
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
    assert results[0]==results[1]


def test_ui_preview_confirm_and_deposit_not_in_total(client,db_session,sample):
    b,t=sample
    assert '2026-09' in client.get(f'/bookings/{b.id}/finance').text
    page=client.get(f'/bookings/{b.id}/finance/start?month=2026-12')
    assert page.status_code==200 and 'Fuera de gestión en RentalManager' in page.text
    assert b.economic_management_start is None
    view=service.preview(db_session,b.id,date(2026,12,1))
    response=client.post(f'/bookings/{b.id}/finance/start',data={'month':'2026-12','expected':view['fingerprint'],'confirmed':'yes'},follow_redirects=False)
    assert response.status_code==303
    page=client.get(f'/bookings/{b.id}/finance')
    assert 'name="include_deposit"' not in page.text
    assert '1000.00' in page.text


def test_manual_future_draft_remains(db_session,sample):
    b,t=sample
    c=finance.create_charge(db_session,b.id,'utilities','Future manual',date(2027,1,1),'20').data
    save(db_session,b)
    assert db_session.get(BookingCharge,c.id).amount==Decimal('20')


def test_economic_activity_after_preview_blocks(db_session,sample):
    b,t=sample;v=service.preview(db_session,b.id,date(2026,12,1))
    finance.create_payment(db_session,b.id,date(2026,11,1),'10','receipt','cash')
    with pytest.raises(ValueError,match='cambiado'):
        service.confirm(db_session,b.id,v['start'],v['fingerprint'],confirmed=True)
    assert b.economic_management_start is None


def test_early_termination_never_restores_excluded_months(db_session,sample,monkeypatch):
    from backend.services.booking_early_termination_service import BookingEarlyTerminationService
    monkeypatch.setattr('backend.services.booking_early_termination_service.business_today',lambda:date(2027,1,10))
    b,t=sample;save(db_session,b)
    early=BookingEarlyTerminationService()
    v=early.preview(db_session,b.id,date(2027,1,10),date(2027,1,15),accept_proration=True)
    assert len(v['plan'])==2
    assert v['plan'][0].service_period_start==date(2026,12,1)
    assert v['plan'][-1].amount==Decimal('193.55')
    assert v['plan'][-1].service_period_end==date(2027,1,16)
    assert finance.repository.list_charges(db_session,b.id)==[]


def test_closed_settlement_protected(db_session,settlement_sample):
    from tests.unit.test_owner_settlement_service import draft,service as settlements
    item=draft(db_session,settlement_sample)
    settlements.close(db_session,item.id,item.fingerprint)
    original=item.snapshot.copy()
    b=settlement_sample['booking']
    v=service.preview(db_session,b.id,date(2026,9,1))
    assert any('liquidaciones cerradas' in msg for msg in v['blockers'])
    with pytest.raises(ValueError):save(db_session,b,date(2026,9,1))
    assert item.snapshot==original and item.status=='closed'
    assert b.economic_management_start is None

from tests.unit.test_owner_settlement_service import sample as settlement_sample
