from datetime import date
from decimal import Decimal

from backend.models.booking import Booking
from backend.models.property import Property
from backend.models.room import Room
from backend.services.booking_service import BookingService
from backend.services.financial_service import FinancialService
from sqlalchemy import select

from backend.models.booking_charge import BookingCharge


def booking(db, *, origin="manual", price=777):
    prop=Property(name="Económica",address="Calle 1",city="Elche",owner="HSI",active=True)
    db.add(prop); db.flush()
    room=Room(property_id=prop.id,code="E01",display_order=1,active=True)
    db.add(room); db.flush()
    item=Booking(room_id=room.id,origin=origin,check_in=date(2026,9,1),check_out=date(2027,6,30),price=price)
    db.add(item); db.commit(); return item


def test_terms_are_decimal_versioned_immutable_and_do_not_copy_legacy_price(db_session):
    item=booking(db_session); service=FinancialService()
    first=service.create_terms_draft(db_session,item.id,date(2026,9,1),Decimal("445.125"))
    assert first.success and first.data.monthly_rent == Decimal("445.13") and first.data.version == 1
    assert service.confirm_terms(db_session,first.data.id).success
    assert service.update_terms_draft(db_session,first.data.id,monthly_rent=Decimal("500")).message == "financial_terms_immutable"
    second=service.create_terms_draft(db_session,item.id,date(2026,10,1),Decimal("500"))
    assert second.data.version == 2
    assert service.confirm_terms(db_session,second.data.id).message == "financial_terms_overlap"
    assert service.legacy_price_candidate(db_session,item.id).amount == Decimal("777.00")
    assert service.due_date_for_month(2027, 2, 31) == date(2027, 2, 28)


def test_supersession_closes_previous_period(db_session):
    item=booking(db_session); service=FinancialService()
    old=service.create_terms_draft(db_session,item.id,date(2026,9,1),Decimal("445")).data
    service.confirm_terms(db_session,old.id)
    rejected = service.supersede_terms(
        db_session, old.id, date(2027, 1, 15), Decimal("475")
    )
    assert rejected.message == "financial_terms_change_requires_full_month"
    result=service.supersede_terms(db_session,old.id,date(2027,1,1),Decimal("475"))
    db_session.refresh(old)
    assert result.success and result.data.version == 2
    assert old.status == "superseded" and old.effective_until == date(2027,1,1)
    assert service.generate_booking_charges(
        db_session, item.id, result.data.id
    ).message == "financial_multiple_terms_not_supported"


def test_partial_allocations_unapplied_balance_refund_and_derived_metrics(db_session):
    item=booking(db_session); service=FinancialService()
    charge=service.create_charge(db_session,item.id,"rent","Septiembre",date(2026,9,1),Decimal("445")).data
    service.post_charge(db_session,charge.id)
    payment=service.create_payment(db_session,item.id,date(2026,9,2),Decimal("500"),"receipt","bank_transfer").data
    service.post_payment(db_session,payment.id)
    assert service.allocate(db_session,payment.id,charge.id,Decimal("200")).success
    balance=service.charge_balance(db_session,charge.id,today=date(2026,9,3))
    summary=service.booking_summary(db_session,item.id,today=date(2026,9,3))
    assert (balance.allocated_amount,balance.outstanding_amount,balance.payment_status,balance.overdue)==(Decimal("200.00"),Decimal("245.00"),"partial",True)
    assert summary.unapplied_balance == Decimal("300.00")
    refund=service.create_payment(db_session,item.id,date(2026,9,3),Decimal("50"),"refund","bank_transfer").data
    service.post_payment(db_session,refund.id)
    assert service.allocate(db_session,refund.id,charge.id,Decimal("50")).success
    assert service.charge_balance(db_session,charge.id).allocated_amount == Decimal("150.00")


def test_allocation_rejects_overallocation_cross_booking_and_float(db_session):
    first=booking(db_session); second=booking(db_session); service=FinancialService()
    charge=service.create_charge(db_session,first.id,"rent","Rent",date(2026,9,1),Decimal("100")).data; service.post_charge(db_session,charge.id)
    payment=service.create_payment(db_session,second.id,date(2026,9,1),Decimal("100"),"receipt","cash").data; service.post_payment(db_session,payment.id)
    assert service.allocate(db_session,payment.id,charge.id,Decimal("10")).message == "allocation_mismatch"
    assert service.create_charge(db_session,first.id,"rent","Bad",date(2026,9,1),10.5).message == "financial_amount_float_not_allowed"


def test_posted_financial_activity_blocks_booking_deletion(db_session):
    item=booking(db_session); finance=FinancialService()
    charge=finance.create_charge(db_session,item.id,"rent","Rent",date(2026,9,1),Decimal("100")).data; finance.post_charge(db_session,charge.id)
    result=BookingService().delete_booking(db_session,item)
    assert not result.success and result.message == "booking_has_posted_financial_activity"
    assert db_session.get(Booking,item.id) is not None


def test_drafts_are_editable_and_posted_records_are_immutable(db_session):
    item=booking(db_session); service=FinancialService()
    charge=service.create_charge(db_session,item.id,"rent","Draft",date(2026,9,1),Decimal("100")).data
    assert service.update_charge_draft(db_session,charge.id,amount=Decimal("110")).data.amount == Decimal("110.00")
    service.post_charge(db_session,charge.id)
    assert service.update_charge_draft(db_session,charge.id,amount=Decimal("120")).message == "charge_immutable"
    payment=service.create_payment(db_session,item.id,date(2026,9,1),Decimal("100"),"receipt","cash").data
    assert service.update_payment_draft(db_session,payment.id,method="bank_transfer").success
    service.post_payment(db_session,payment.id)
    assert service.update_payment_draft(db_session,payment.id,amount=Decimal("90")).message == "payment_immutable"


def test_imported_booking_can_have_local_ledger(db_session):
    item=booking(db_session,origin="housinganywhere"); service=FinancialService()
    assert service.create_terms_draft(db_session,item.id,date(2026,9,1),Decimal("445")).success
    assert item.price == Decimal("777.00")


def test_monthly_preview_uses_half_open_calendar_months_and_rounds_each_charge():
    service = FinancialService()
    full = service.preview_monthly_rent(
        check_in=date(2026, 9, 1), check_out=date(2026, 10, 1),
        monthly_rent=Decimal("400"), usual_due_day=1, terms_id=1,
    )
    entry_partial = service.preview_monthly_rent(
        check_in=date(2026, 9, 16), check_out=date(2026, 10, 1),
        monthly_rent=Decimal("400"), usual_due_day=1, terms_id=1,
    )
    exit_partial = service.preview_monthly_rent(
        check_in=date(2026, 9, 1), check_out=date(2026, 9, 16),
        monthly_rent=Decimal("400"), usual_due_day=1, terms_id=1,
    )
    same_month = service.preview_monthly_rent(
        check_in=date(2026, 9, 16), check_out=date(2026, 9, 21),
        monthly_rent=Decimal("400"), usual_due_day=20, terms_id=1,
    )

    assert full[0].amount == Decimal("400.00")
    assert entry_partial[0].amount == Decimal("200.00")
    assert entry_partial[0].due_date == date(2026, 9, 16)
    assert exit_partial[0].amount == Decimal("200.00")
    assert same_month[0].amount == Decimal("66.67")
    assert same_month[0].service_period_end == date(2026, 9, 21)
    assert same_month[0].due_date == date(2026, 9, 20)


def test_monthly_preview_handles_february_year_boundary_and_due_days_29_to_31():
    service = FinancialService()
    normal = service.preview_monthly_rent(
        check_in=date(2027, 2, 1), check_out=date(2027, 3, 1),
        monthly_rent=Decimal("400"), usual_due_day=31, terms_id=1,
    )
    leap = service.preview_monthly_rent(
        check_in=date(2028, 2, 1), check_out=date(2028, 3, 1),
        monthly_rent=Decimal("400"), usual_due_day=30, terms_id=1,
    )
    crossing = service.preview_monthly_rent(
        check_in=date(2026, 12, 15), check_out=date(2027, 2, 2),
        monthly_rent=Decimal("310"), usual_due_day=29, terms_id=1,
    )

    assert (normal[0].amount, normal[0].due_date) == (Decimal("400.00"), date(2027, 2, 28))
    assert (leap[0].amount, leap[0].due_date) == (Decimal("400.00"), date(2028, 2, 29))
    assert [row.service_period_start for row in crossing] == [date(2026, 12, 15), date(2027, 1, 1), date(2027, 2, 1)]
    assert crossing[0].due_date == date(2026, 12, 29)
    assert crossing[-1].amount == Decimal("11.07")


def test_generation_is_atomic_idempotent_can_include_deposit_and_post(db_session):
    item = booking(db_session)
    item.check_out = date(2026, 11, 1)
    db_session.commit()
    service = FinancialService()
    terms = service.create_terms_draft(
        db_session, item.id, item.check_in, Decimal("445"),
        deposit_agreed=Decimal("400"), usual_due_day=31,
    ).data
    service.confirm_terms(db_session, terms.id)

    first = service.generate_booking_charges(
        db_session, item.id, terms.id, include_deposit=True
    )
    second = service.generate_booking_charges(
        db_session, item.id, terms.id, include_deposit=True
    )
    charges = db_session.scalars(
        select(BookingCharge).where(BookingCharge.booking_id == item.id)
    ).all()

    assert first.success and len(first.data) == 3
    assert second.success and second.data == []
    assert {charge.type for charge in charges} == {"rent", "security_deposit"}
    assert all(charge.lifecycle == "draft" for charge in charges)
    assert next(c for c in charges if c.type == "rent").due_date == date(2026, 9, 30)
    assert next(c for c in charges if c.type == "security_deposit").due_date == item.check_in
    assert service.post_generated_drafts(db_session, item.id).success
    assert all(charge.lifecycle == "posted" for charge in charges)


def test_date_changes_only_mark_generated_records_stale_until_explicit_regeneration(db_session):
    item = booking(db_session)
    item.check_out = date(2026, 11, 1)
    db_session.commit()
    service = FinancialService()
    terms = service.create_terms_draft(db_session, item.id, item.check_in, Decimal("445")).data
    service.confirm_terms(db_session, terms.id)
    service.generate_booking_charges(db_session, item.id, terms.id)
    original_ids = [charge.id for charge in service.repository.list_charges(db_session, item.id)]

    item.check_out = date(2026, 12, 1)
    db_session.commit()
    assert service.generation_state(db_session, item, terms)["drafts_stale"]
    assert [charge.id for charge in service.repository.list_charges(db_session, item.id)] == original_ids

    regenerated = service.regenerate_draft_charges(db_session, item.id, terms.id)
    assert regenerated.success and len(regenerated.data) == 3
    assert not service.generation_state(db_session, item, terms)["drafts_stale"]

    service.post_generated_drafts(db_session, item.id)
    item.check_in = date(2026, 9, 20)
    db_session.commit()
    state = service.generation_state(db_session, item, terms)
    assert state["posted_mismatch"] and not state["drafts_stale"]


def test_deposit_is_never_generated_without_explicit_inclusion(db_session):
    item = booking(db_session)
    item.check_out = date(2026, 10, 1)
    db_session.commit()
    service = FinancialService()
    terms = service.create_terms_draft(
        db_session, item.id, item.check_in, Decimal("445"),
        deposit_agreed=Decimal("400"),
    ).data
    service.confirm_terms(db_session, terms.id)

    result = service.generate_booking_charges(db_session, item.id, terms.id)

    assert result.success and [charge.type for charge in result.data] == ["rent"]
