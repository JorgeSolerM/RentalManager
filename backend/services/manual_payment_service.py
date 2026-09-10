from decimal import Decimal
from hashlib import sha256
import json
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from backend.core.business_time import business_today
from backend.models.booking import Booking
from backend.models.payment import Payment
from backend.models.payment_allocation import PaymentAllocation
from backend.models.payment_registration import PaymentRegistration
from backend.services.financial_service import FinancialService, ZERO
from backend.services.financial_transaction import financial_transaction

METHODS = {'cash': 'Efectivo', 'bank_transfer': 'Transferencia', 'other': 'Otro'}
ALL_METHODS = {**METHODS, 'sepa_direct_debit': 'SEPA / domiciliación', 'card_or_platform': 'Tarjeta / plataforma'}


class ManualPaymentService:
    def __init__(self):
        self.finance = FinancialService()

    def pending(self, db, booking_id):
        return [(c, self.finance.charge_balance(db, c.id).outstanding_amount)
                for c in self.finance.repository.list_charges(db, booking_id)
                if c.lifecycle == 'posted' and c.direction == 'debit'
                and self.finance.charge_balance(db, c.id).outstanding_amount > ZERO]

    def propose(self, db, booking_id, amount):
        remaining = self.finance._money(amount, allow_zero=False)
        rows = []
        for charge, outstanding in self.pending(db, booking_id):
            proposed = min(remaining, outstanding)
            rows.append((charge, outstanding, proposed))
            remaining -= proposed
        return rows, remaining

    def register(self, db, booking_id, *, amount, effective_date, method, allocations,
                 request_key, reference=None, notes=None, allow_unallocated=False):
        try:
            key = str(UUID(request_key))
            amount = self.finance._money(amount, allow_zero=False)
            pairs = [(int(i), self.finance._money(v, allow_zero=False)) for i, v in allocations]
        except (ValueError, TypeError, ArithmeticError):
            raise ValueError('Importe o distribución no válidos.') from None
        if method not in METHODS or effective_date > business_today() or amount > Decimal('9999999999.99'):
            raise ValueError('Revise el método, importe y fecha efectiva del cobro.')
        if len({i for i, _ in pairs}) != len(pairs):
            raise ValueError('Hay cargos duplicados en la distribución.')
        total = sum((v for _, v in pairs), ZERO)
        if total > amount or (total != amount and not allow_unallocated):
            raise ValueError('Revise la distribución; confirme expresamente cualquier saldo sin aplicar.')
        reference = (reference or '').strip() or None
        notes = (notes or '').strip() or None
        if (reference and len(reference) > 255) or (notes and len(notes) > 2000):
            raise ValueError('Referencia o nota demasiado larga.')
        fingerprint = sha256(json.dumps([booking_id,str(amount),str(effective_date),method,
            sorted((i,str(v)) for i,v in pairs),reference,notes,allow_unallocated]).encode()).hexdigest()
        with financial_transaction(db):
            previous = db.get(PaymentRegistration, key)
            if previous:
                if previous.fingerprint != fingerprint:
                    raise ValueError('Esta solicitud ya se utilizó con otros datos.')
                return db.get(Payment, previous.payment_id)
            if db.get(Booking, booking_id) is None:
                raise ValueError('Reserva no encontrada.')
            pending = {c.id: (c, value) for c, value in self.pending(db, booking_id)}
            for charge_id, value in pairs:
                if charge_id not in pending or value > pending[charge_id][1] or pending[charge_id][0].currency != 'EUR':
                    raise ValueError('El saldo de un cargo ha cambiado o no pertenece a esta reserva. Revise la distribución.')
            payment = Payment(booking_id=booking_id, amount=amount, currency='EUR',
                effective_date=effective_date, method=method, direction='receipt',
                lifecycle='posted', posted_at=self.finance._now(), external_reference=reference, notes=notes)
            db.add(payment); db.flush()
            for charge_id, value in pairs:
                db.add(PaymentAllocation(payment_id=payment.id, charge_id=charge_id, amount=value))
            db.add(PaymentRegistration(request_key=key, fingerprint=fingerprint, payment_id=payment.id))
        return payment

    def history(self, db, booking_id):
        return list(db.scalars(select(Payment).where(Payment.booking_id == booking_id)
            .options(selectinload(Payment.allocations).joinedload(PaymentAllocation.charge))
            .order_by(Payment.effective_date, Payment.id)))
