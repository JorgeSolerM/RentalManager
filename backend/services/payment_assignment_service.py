"""Assign only the unconsumed balance of existing receipts, atomically."""
from hashlib import sha256
import json
from uuid import UUID
from sqlalchemy import select, or_
from backend.models.payment import Payment
from backend.models.booking_charge import BookingCharge
from backend.models.payment_allocation import PaymentAllocation
from backend.models.payment_allocation_operation import PaymentAllocationOperation
from backend.models.owner_settlement import OwnerSettlementLine
from backend.models.sepa_collection import SepaDebit, SepaDebitChargeAllocation
from backend.services.financial_service import FinancialService, ZERO
from backend.services.financial_transaction import financial_transaction


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class PaymentAssignmentService:
    def __init__(self):
        self.finance = FinancialService()

    def allocations(self, db, payment_id):
        return list(db.scalars(select(PaymentAllocation).where(PaymentAllocation.payment_id == payment_id).order_by(PaymentAllocation.id)))

    def available(self, db, payment):
        return payment.amount - sum((a.amount for a in self.allocations(db, payment.id)), ZERO)

    def settled(self, db, *, payment_id=None, charge_id=None):
        query = select(OwnerSettlementLine.id).join(PaymentAllocation,
            OwnerSettlementLine.payment_allocation_id == PaymentAllocation.id)
        query = query.where(PaymentAllocation.payment_id == payment_id) if payment_id is not None else query.where(PaymentAllocation.charge_id == charge_id)
        return db.scalar(query.limit(1)) is not None

    def payment_blocker(self, db, payment):
        if payment.lifecycle != 'posted' or payment.direction != 'receipt':
            return 'Solo se asignan cobros confirmados; no borradores, anulaciones ni devoluciones.'
        if self.settled(db, payment_id=payment.id):
            return 'Este cobro participa en una liquidación cerrada. Requiere revisión independiente.'
        if db.scalar(select(Payment.id).where(Payment.corrects_payment_id == payment.id, Payment.lifecycle != 'void').limit(1)):
            return 'El cobro tiene una devolución o corrección vinculada. Requiere revisión independiente.'
        if db.scalar(select(SepaDebit.id).where(or_(SepaDebit.payment_id == payment.id, SepaDebit.return_payment_id == payment.id)).limit(1)):
            return 'El cobro pertenece a un adeudo SEPA; su distribución bancaria se conserva.'
        return None

    def charge_blocker(self, db, charge):
        if self.settled(db, charge_id=charge.id):
            return 'Cargo vinculado a una liquidación cerrada.'
        if db.scalar(select(SepaDebitChargeAllocation.id).where(
                SepaDebitChargeAllocation.charge_id == charge.id, SepaDebitChargeAllocation.reserved.is_(True)).limit(1)):
            return 'Cargo reservado en una remesa activa. Revise la remesa antes de asignar.'
        return None

    def unassigned(self, db, booking_id):
        result = []
        for payment in db.scalars(select(Payment).where(Payment.booking_id == booking_id,
                Payment.lifecycle == 'posted', Payment.direction == 'receipt').order_by(Payment.effective_date, Payment.id)):
            available = self.available(db, payment)
            if available > ZERO:
                result.append(dict(payment=payment, available=available, assigned=payment.amount-available,
                                   blocker=self.payment_blocker(db, payment)))
        return result

    def form(self, db, booking_id, payment_id):
        payment = db.get(Payment, payment_id)
        if payment is None or payment.booking_id != booking_id:
            raise ValueError('Cobro no encontrado en esta reserva.')
        rows = []
        for charge in self.finance.repository.list_charges(db, booking_id):
            balance = self.finance.charge_balance(db, charge.id)
            if charge.lifecycle == 'posted' and charge.direction == 'debit' and charge.currency == payment.currency and balance.outstanding_amount > ZERO:
                rows.append(dict(charge=charge, outstanding=balance.outstanding_amount,
                                 blocker=self.charge_blocker(db, charge)))
        history = list(db.scalars(select(PaymentAllocationOperation).where(
            PaymentAllocationOperation.payment_id == payment_id).order_by(PaymentAllocationOperation.created_at, PaymentAllocationOperation.request_key)))
        return dict(payment=payment, available=self.available(db, payment), rows=rows,
                    blocker=self.payment_blocker(db, payment), history=history)

    def normalize(self, pairs):
        try:
            result = sorted((int(i), self.finance._money(v, allow_zero=False)) for i, v in pairs)
        except (ValueError, TypeError, ArithmeticError):
            raise ValueError('Revise los importes de asignación.') from None
        if not result or len({i for i, _ in result}) != len(result):
            raise ValueError('Seleccione al menos un cargo, sin repetirlo.')
        return result

    def preview(self, db, booking_id, payment_id, pairs):
        pairs = self.normalize(pairs)
        view = self.form(db, booking_id, payment_id)
        if view['blocker']:
            raise ValueError(view['blocker'])
        total = sum((v for _, v in pairs), ZERO)
        if total > view['available']:
            raise ValueError('El importe supera el saldo disponible del cobro.')
        pending = {r['charge'].id:r for r in view['rows']}
        selected = []
        for cid, amount in pairs:
            row = pending.get(cid)
            if row is None or amount > row['outstanding']:
                raise ValueError('Cargo ajeno, no pendiente o con saldo insuficiente. Revise la distribución.')
            if row['blocker']:
                raise ValueError(row['blocker'])
            selected.append(dict(**row, amount=amount, remaining=row['outstanding']-amount))
        p = view['payment']
        state = dict(payment=[str(getattr(p,c.name)) for c in p.__table__.columns],
            allocations=[(a.id,a.charge_id,str(a.amount)) for a in self.allocations(db,p.id)],
            rows=[(r['charge'].id,str(r['outstanding']),str(r['amount']),r['charge'].concept,str(r['charge'].due_date)) for r in selected])
        return dict(**view, selected=selected, total=total, remaining=view['available']-total, fingerprint=digest(state))

    def confirm(self, db, booking_id, payment_id, pairs, *, request_key, expected, confirmed=False):
        if not confirmed:
            raise ValueError('Confirme expresamente la asignación revisada.')
        try:
            key = str(UUID(request_key))
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Solicitud no válida. Revise nuevamente el cobro.') from None
        pairs = self.normalize(pairs)
        fingerprint = digest([booking_id,payment_id,[(i,str(v)) for i,v in pairs]])
        with financial_transaction(db):
            previous = db.get(PaymentAllocationOperation, key)
            if previous:
                if previous.fingerprint != fingerprint:
                    raise ValueError('Esta solicitud ya se utilizó con otros datos.')
                return previous
            view = self.preview(db, booking_id, payment_id, pairs)
            if view['fingerprint'] != expected:
                raise ValueError('Los saldos han cambiado. Revise nuevamente la asignación.')
            existing = {a.charge_id:a for a in self.allocations(db, payment_id)}
            changes = []
            for cid, value in pairs:
                allocation = existing.get(cid)
                before = allocation.amount if allocation else ZERO
                if allocation is None:
                    allocation = PaymentAllocation(payment_id=payment_id,charge_id=cid,amount=value)
                    db.add(allocation)
                else:
                    allocation.amount += value
                db.flush()
                changes.append(dict(allocation_id=allocation.id,charge_id=cid,before=str(before),
                                    added=str(value),after=str(allocation.amount)))
            operation = PaymentAllocationOperation(request_key=key,payment_id=payment_id,
                fingerprint=fingerprint,reviewed_state=expected,amount=view['total'],changes=changes)
            db.add(operation)
        return operation
