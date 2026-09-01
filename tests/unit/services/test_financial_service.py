from datetime import date
from decimal import Decimal

from backend.models.booking import Booking
from backend.models.property import Property
from backend.models.room import Room
from backend.services.booking_service import BookingService
from backend.services.financial_service import FinancialService


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
    result=service.supersede_terms(db_session,old.id,date(2027,1,1),Decimal("475"))
    db_session.refresh(old)
    assert result.success and result.data.version == 2
    assert old.status == "superseded" and old.effective_until == date(2027,1,1)


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
