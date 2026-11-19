"""Audited void/replacement of receipts, never a fictitious bank refund."""
from uuid import UUID
from sqlalchemy import select, or_
from backend.models.payment import Payment
from backend.models.payment_allocation import PaymentAllocation
from backend.models.payment_correction_operation import PaymentCorrectionOperation
from backend.models.owner_settlement import PaymentCustody
from backend.services.financial_service import FinancialService, ZERO
from backend.services.payment_assignment_service import PaymentAssignmentService, digest
from backend.services.financial_transaction import financial_transaction


class PaymentCorrectionService:
    def __init__(self):
        self.finance = FinancialService()
        self.assignments = PaymentAssignmentService()

    def history(self, db, booking_id):
        return list(db.scalars(select(PaymentCorrectionOperation).join(Payment,
            Payment.id == PaymentCorrectionOperation.original_payment_id).where(Payment.booking_id == booking_id)
            .order_by(PaymentCorrectionOperation.created_at, PaymentCorrectionOperation.request_key)))

    def form(self, db, booking_id, payment_id):
        payment = db.get(Payment, payment_id)
        if payment is None or payment.booking_id != booking_id:
            raise ValueError('Cobro no encontrado en esta reserva.')
        blockers = []
        blocked = self.assignments.payment_blocker(db, payment)
        if blocked:
            blockers.append(blocked)
        if payment.method == 'sepa_direct_debit':
            blockers.append('Los cobros SEPA requieren su procedimiento específico.')
        if payment.currency != 'EUR':
            blockers.append('Esta operación solo admite EUR.')
        if payment.corrects_payment_id and not db.scalar(select(PaymentCorrectionOperation.request_key).where(
                PaymentCorrectionOperation.replacement_payment_id == payment.id)):
            blockers.append('El movimiento ya es una corrección de origen no identificado.')
        if db.scalar(select(PaymentCorrectionOperation.request_key).where(PaymentCorrectionOperation.original_payment_id == payment.id)):
            blockers.append('El cobro ya fue anulado o sustituido. Consulte su historial.')
        custodies = list(db.scalars(select(PaymentCustody).where(PaymentCustody.payment_id == payment_id)))
        if len(custodies) != 1 or custodies[0].amount != payment.amount:
            blockers.append('Custodia ausente, ambigua o incompleta. Identifique quién recibió el dinero antes de corregir.')
        allocations = self.assignments.allocations(db, payment_id)
        rows = []
        for allocation in allocations:
            charge = allocation.charge
            blocker = self.assignments.charge_blocker(db, charge)
            if blocker:
                blockers.append(blocker)
            if (charge.booking_id != booking_id or charge.currency != payment.currency
                    or charge.lifecycle != 'posted' or charge.direction != 'debit'):
                blockers.append('Hay asignaciones incompatibles con la reserva o el estado de sus cargos.')
            balance = self.finance.charge_balance(db, charge.id)
            rows.append(dict(allocation=allocation, charge=charge, balance=balance))
        assigned = sum((a.amount for a in allocations), ZERO)
        if assigned > payment.amount:
            blockers.append('El cobro tiene asignaciones superiores al importe registrado.')
        return dict(payment=payment, blockers=list(dict.fromkeys(blockers)), rows=rows,
                    assigned=assigned, unassigned=payment.amount-assigned, custodies=custodies,
                    history=self.history(db, booking_id))

    def normalize(self, kind, amount, reason, pairs):
        reason = (reason or '').strip()
        if not reason or len(reason) > 1000:
            raise ValueError('Indique un motivo obligatorio de hasta 1000 caracteres.')
        if kind not in ('void', 'replace'):
            raise ValueError('Tipo de operación no válido.')
        try:
            value = ZERO if kind == 'void' else self.finance._money(amount, allow_zero=False)
            normalized = None if pairs is None else sorted((int(i), self.finance._money(v)) for i,v in pairs)
        except (ValueError, TypeError, ArithmeticError):
            raise ValueError('Revise el nuevo importe y la distribución.') from None
        if value > self.finance._money('9999999999.99'):
            raise ValueError('Importe fuera de rango.')
        if normalized is not None and len(normalized) != len({i for i,_ in normalized}):
            raise ValueError('No repita cargos en la distribución.')
        return value, reason, normalized

    def preview(self, db, booking_id, payment_id, *, kind, amount=None, reason='', pairs=None, redistributed=False):
        value, reason, pairs = self.normalize(kind, amount, reason, pairs)
        view = self.form(db, booking_id, payment_id)
        if view['blockers']:
            raise ValueError(' '.join(view['blockers']))
        original = view['payment']
        if kind == 'replace' and value == original.amount:
            raise ValueError('El nuevo importe debe ser distinto del original.')
        old = {r['charge'].id:r['allocation'].amount for r in view['rows']}
        if pairs is not None and any(i not in old for i,_ in pairs):
            raise ValueError('La corrección solo admite cargos originalmente asignados de esta reserva.')
        if kind == 'void':
            revised = {i:ZERO for i in old}
        elif value >= view['assigned']:
            revised = old.copy()
            if pairs is not None and {i:v for i,v in pairs if v} != {i:v for i,v in old.items() if v}:
                raise ValueError('Conserve las asignaciones actuales; la diferencia queda en el saldo libre.')
        else:
            if not redistributed or pairs is None:
                raise ValueError('El nuevo importe no cubre lo asignado. Revise y acepte expresamente la distribución por cargo.')
            revised = {i:ZERO for i in old};revised.update(pairs)
        total = sum(revised.values(), ZERO)
        if total > value:
            raise ValueError('Las asignaciones superan el nuevo importe.')
        effects = []
        for row in view['rows']:
            cid = row['charge'].id
            net = row['balance'].allocated_amount - old[cid] + revised[cid]
            if net < ZERO or net > row['charge'].amount:
                raise ValueError('La corrección produciría un saldo de cargo inválido. Revise sus movimientos.')
            effects.append(dict(charge=row['charge'], before=old[cid], after=revised[cid],
                outstanding_before=row['balance'].outstanding_amount, outstanding_after=row['charge'].amount-net))
        summary = self.finance.booking_summary(db, booking_id)
        received_after = summary.received_total - original.amount + value
        unapplied_after = summary.unapplied_balance - view['unassigned'] + value-total
        if received_after < ZERO or unapplied_after < ZERO:
            raise ValueError('La corrección produciría un saldo negativo incompatible con otros movimientos.')
        def record(obj):
            return {c.name:str(getattr(obj,c.name)) for c in obj.__table__.columns}
        state = dict(payment=record(original), allocations=[record(r['allocation']) for r in view['rows']],
            charges=[record(r['charge']) for r in view['rows']], balances=[str(r['balance']) for r in view['rows']],
            custody=[record(c) for c in view['custodies']], summary=str(summary),
            kind=kind, amount=str(value), reason=reason, revised=[(i,str(v)) for i,v in sorted(revised.items())])
        return dict(**view, kind=kind, amount=value, reason=reason, effects=effects,
                    remaining=value-total, received_before=summary.received_total, received_after=received_after,
                    fingerprint=digest(state), revised=sorted(revised.items()), redistributed=redistributed)

    def confirm(self, db, booking_id, payment_id, *, request_key, expected, confirmed=False, **values):
        if not confirmed:
            raise ValueError('Confirme expresamente la corrección revisada.')
        try:
            key = str(UUID(request_key))
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Solicitud no válida. Revise de nuevo.') from None
        value, reason, pairs = self.normalize(values['kind'], values.get('amount'), values.get('reason'), values.get('pairs'))
        fingerprint = digest([booking_id,payment_id,values['kind'],str(value),reason,
                              None if pairs is None else [(i,str(v)) for i,v in pairs],bool(values.get('redistributed'))])
        with financial_transaction(db):
            previous = db.get(PaymentCorrectionOperation, key)
            if previous:
                if previous.fingerprint != fingerprint:
                    raise ValueError('Esta solicitud ya se utilizó con otros datos.')
                return previous
            review = self.preview(db, booking_id, payment_id, **values)
            if review['fingerprint'] != expected:
                raise ValueError('Los datos han cambiado. Revise nuevamente la corrección.')
            original = review['payment'];custody = review['custodies'][0]
            now = self.finance._now()
            original.lifecycle = 'void';original.voided_at = now
            replacement = None
            if values['kind'] == 'replace':
                replacement = Payment(booking_id=original.booking_id,effective_date=original.effective_date,
                    amount=value,currency=original.currency,direction='receipt',method=original.method,
                    external_reference=original.external_reference,notes=original.notes,
                    lifecycle='posted',posted_at=now,corrects_payment_id=original.id)
                db.add(replacement);db.flush()
                db.add(PaymentCustody(payment_id=replacement.id,actor=custody.actor,owner_id=custody.owner_id,
                                     bank_account_id=custody.bank_account_id,amount=value))
                for cid,assigned in review['revised']:
                    if assigned > ZERO:
                        db.add(PaymentAllocation(payment_id=replacement.id,charge_id=cid,amount=assigned))
            db.flush()
            operation = PaymentCorrectionOperation(request_key=key,original_payment_id=original.id,
                replacement_payment_id=replacement.id if replacement else None,kind=values['kind'],reason=reason,
                before_amount=original.amount,after_amount=value,fingerprint=fingerprint,reviewed_state=expected,
                distribution=[dict(charge_id=r['charge'].id,before=str(r['before']),after=str(r['after'])) for r in review['effects']],
                custody_snapshot=dict(actor=custody.actor,owner_id=custody.owner_id,bank_account_id=custody.bank_account_id,
                                      before=str(custody.amount),after=str(value)))
            db.add(operation)
        return operation
