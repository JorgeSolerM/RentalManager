"""Explicitly reviewed full-stay plans; no payments and no implicit corrections."""
import hashlib
import json

from backend.models.booking import Booking
from backend.models.booking_charge import BookingCharge
from backend.services.financial_service import FinancialService
from backend.services.financial_transaction import financial_transaction


class CollectionPlanService:
    def __init__(self):
        self.finance = FinancialService()

    @staticmethod
    def signature(row):
        return tuple(str(getattr(row, key)) for key in (
            'type', 'concept', 'service_period_start', 'service_period_end',
            'due_date', 'amount', 'currency', 'generation_key'))

    def review_token(self, booking, terms):
        rows = self.finance.preview_for_booking(booking, terms, include_deposit=True)
        value = [booking.id, terms.id, [self.signature(row) for row in rows]]
        return hashlib.sha256(json.dumps(value).encode()).hexdigest()

    def generate(self, db, booking_id, terms_id, *, review_token, include_deposit=False):
        with financial_transaction(db):
            booking = db.get(Booking, booking_id)
            terms = self.finance.repository.get_terms(db, terms_id)
            if not booking or not terms:
                raise ValueError('Reserva o condiciones no encontradas.')
            if len(self.finance.repository.list_terms(db, booking_id)) != 1:
                raise ValueError('Las múltiples versiones de renta requieren revisión y no están habilitadas.')
            if review_token != self.review_token(booking, terms):
                raise ValueError('El calendario ha cambiado. Recargue y revise el plan antes de confirmarlo.')
            rows = self.finance.preview_for_booking(booking, terms, include_deposit=include_deposit)
            expected = {row.generation_key: row for row in rows}
            existing = {c.generation_key: c for c in self.finance.repository.list_charges(db, booking_id)
                        if c.generation_key}
            for key, charge in existing.items():
                if (key not in expected or charge.lifecycle == 'void' or charge.direction != 'debit'
                        or self.signature(charge) != self.signature(expected[key])):
                    raise ValueError('Existen cargos que no coinciden con el plan revisado. Revise explícitamente los borradores o las correcciones; no se ha modificado ningún cargo.')
            now = self.finance._now()
            for row in rows:
                charge = existing.get(row.generation_key)
                if charge is None:
                    charge = BookingCharge(booking_id=booking_id, financial_terms_id=terms_id,
                        direction='debit', **{key: getattr(row, key) for key in (
                            'type', 'concept', 'service_period_start', 'service_period_end',
                            'due_date', 'amount', 'currency', 'generation_key')})
                    db.add(charge)
                if charge.lifecycle != 'posted':
                    charge.lifecycle = 'posted'
                    charge.posted_at = now
            db.flush()
