"""Explicit accounting cutoff. Never changes occupation or posted history."""
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json

from sqlalchemy import select
from backend.models.booking import Booking
from backend.models.payment_allocation import PaymentAllocation
from backend.models.owner_settlement import OwnerSettlementLine
from backend.models.sepa_collection import SepaDebitChargeAllocation
from backend.services.financial_service import FinancialService
from backend.services.financial_transaction import financial_transaction


class EconomicStartService:
    def __init__(self):
        self.finance = FinancialService()

    def preview(self, db, booking_id, start):
        booking = db.get(Booking, booking_id)
        if booking is None:
            raise ValueError('Reserva no encontrada.')
        if not isinstance(start, date) or start.day != 1:
            raise ValueError('El inicio debe ser el primer día de un mes.')
        if start < booking.check_in.replace(day=1) or start >= booking.economic_check_out:
            raise ValueError('El mes debe pertenecer al periodo económico de la reserva.')
        terms = self.finance.repository.list_terms(db, booking_id)
        charges = self.finance.repository.list_charges(db, booking_id)
        payments = self.finance.repository.list_payments(db, booking_id)
        charge_ids = [c.id for c in charges]
        allocations = list(db.scalars(select(PaymentAllocation).where(PaymentAllocation.charge_id.in_(charge_ids))))
        lines = list(db.scalars(select(OwnerSettlementLine).where(OwnerSettlementLine.payment_allocation_id.in_([a.id for a in allocations]))))
        debits = list(db.scalars(select(SepaDebitChargeAllocation).where(SepaDebitChargeAllocation.charge_id.in_(charge_ids))))
        blockers = []
        if any(c.lifecycle != 'draft' for c in charges) or payments or allocations:
            blockers.append('Existe histórico económico o cargos contabilizados. El inicio no puede cambiarse ni ocultar esos movimientos.')
        if lines:
            blockers.append('Existen liquidaciones cerradas relacionadas; su histórico se conserva.')
        if debits:
            blockers.append('Existen vínculos con adeudos; requieren revisión independiente.')
        if len(terms) != 1 or terms[0].status != 'confirmed':
            blockers.append('Confirme una única versión de condiciones económicas para revisar los importes.')
        rows = []
        if len(terms) == 1:
            t = terms[0]
            rows = self.finance.preview_monthly_rent(check_in=booking.check_in, check_out=booking.economic_check_out,
                monthly_rent=t.monthly_rent, usual_due_day=t.usual_due_day, terms_id=t.id, currency=t.currency)
        included = self.finance.managed_rows(rows, start)
        excluded = [r for r in rows if r not in included]
        affected = [c for c in charges if (c.service_period_start is not None and c.service_period_start < start)
                    or (c.service_period_start is None and c.due_date < start)]
        automatic_keys = {r.generation_key for r in rows}
        automatic_keys.update(f'security-deposit:terms-{t.id}' for t in terms)
        manual = [c for c in affected if c.lifecycle == 'draft' and c.generation_key not in automatic_keys]
        if manual:
            blockers.append('Hay borradores manuales afectados. Revise esos cargos antes de cambiar el inicio.')
        removed = [c for c in affected if c.lifecycle == 'draft' and c.generation_key in automatic_keys]
        existing_keys = {c.generation_key for c in charges if c not in removed}
        def record(obj):
            return {column.name: str(getattr(obj, column.name)) for column in obj.__table__.columns}
        # Hash state, never store contact/banking values in a review token.
        state = {'booking': [booking.id, str(booking.check_in), str(booking.economic_check_out),
                             str(booking.economic_management_start), str(booking.economic_management_start_configured_at)],
                 'start': str(start), 'terms': [record(t) for t in terms], 'charges': [record(c) for c in charges],
                 'payments': [record(p) for p in payments], 'allocations': [record(a) for a in allocations],
                 'settlements': [r.id for r in lines], 'debits': [r.id for r in debits]}
        return dict(booking=booking, start=start, included=included, excluded=excluded, charges=charges,
                    blockers=blockers, removed=removed,
                    total=sum((r.amount for r in included), Decimal('0.00')),
                    new_total=sum((r.amount for r in included if r.generation_key not in existing_keys), Decimal('0.00')),
                    deposit_excluded=bool(terms and terms[0].deposit_agreed and booking.check_in < start),
                    fingerprint=hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest())

    def confirm(self, db, booking_id, start, expected, *, confirmed=False, replace_drafts=False):
        if not confirmed:
            raise ValueError('Confirme expresamente el inicio de gestión económica.')
        with financial_transaction(db):
            booking = db.get(Booking, booking_id)
            if booking is not None and booking.economic_management_start == start:
                return booking  # Repeated confirmation has no further effects, even after posting.
            view = self.preview(db, booking_id, start)
            if expected != view['fingerprint']:
                raise ValueError('Los datos han cambiado. Revise nuevamente el inicio de gestión.')
            if view['blockers']:
                raise ValueError(' '.join(view['blockers']))
            if view['removed'] and not replace_drafts:
                raise ValueError('Confirme la retirada de los borradores automáticos excluidos.')
            for charge in view['removed']:
                db.delete(charge)
            booking.economic_management_start = start
            booking.economic_management_start_configured_at = datetime.now(timezone.utc).replace(tzinfo=None)
        return booking
