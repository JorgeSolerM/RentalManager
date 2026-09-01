from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.booking_charge import BookingCharge
from backend.models.booking_financial_terms import BookingFinancialTerms
from backend.models.payment import Payment
from backend.models.payment_allocation import PaymentAllocation


class FinancialRepository:
    def next_terms_version(self, db: Session, booking_id: int) -> int:
        return (db.scalar(select(func.max(BookingFinancialTerms.version)).where(BookingFinancialTerms.booking_id == booking_id)) or 0) + 1

    def get_terms(self, db: Session, terms_id: int):
        return db.get(BookingFinancialTerms, terms_id)

    def overlapping_confirmed_terms(self, db: Session, terms: BookingFinancialTerms):
        statement = select(BookingFinancialTerms).where(
            BookingFinancialTerms.booking_id == terms.booking_id,
            BookingFinancialTerms.id != terms.id,
            BookingFinancialTerms.status.in_(("confirmed", "superseded")),
            (BookingFinancialTerms.effective_until.is_(None) | (BookingFinancialTerms.effective_until > terms.effective_from)),
        )
        if terms.effective_until is not None:
            statement = statement.where(BookingFinancialTerms.effective_from < terms.effective_until)
        return db.scalar(statement)

    def get_charge(self, db: Session, charge_id: int):
        return db.get(BookingCharge, charge_id)

    def get_payment(self, db: Session, payment_id: int):
        return db.get(Payment, payment_id)

    def allocation_total_for_payment(self, db: Session, payment_id: int):
        return db.scalar(select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(PaymentAllocation.payment_id == payment_id))

    def allocations_for_charge(self, db: Session, charge_id: int):
        return db.execute(select(PaymentAllocation, Payment).join(Payment).where(PaymentAllocation.charge_id == charge_id)).all()

    def list_charges(self, db: Session, booking_id: int):
        return db.scalars(select(BookingCharge).where(BookingCharge.booking_id == booking_id)).all()

    def list_payments(self, db: Session, booking_id: int):
        return db.scalars(select(Payment).where(Payment.booking_id == booking_id)).all()

    def has_posted_activity(self, db: Session, booking_id: int) -> bool:
        charge = db.scalar(select(BookingCharge.id).where(BookingCharge.booking_id == booking_id, BookingCharge.lifecycle == "posted").limit(1))
        payment = db.scalar(select(Payment.id).where(Payment.booking_id == booking_id, Payment.lifecycle == "posted").limit(1))
        return charge is not None or payment is not None

    def has_any_records(self, db: Session, booking_id: int) -> bool:
        for model in (BookingFinancialTerms, BookingCharge, Payment):
            if db.scalar(select(model.id).where(model.booking_id == booking_id).limit(1)) is not None:
                return True
        return False
