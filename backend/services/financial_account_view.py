"""Read-only presentation of the existing ledger and explicit allocations."""
from decimal import Decimal

from sqlalchemy import or_, select
from backend.models.sepa_collection import SepaDebit, SepaBatchGroup


def account_view(db, charges, balances, payments, today):
    movements = {charge.id: [] for charge in charges}
    payment_ids = [payment.id for payment in payments]
    batches = {}
    if payment_ids:
        for debit, batch_id in db.execute(select(SepaDebit, SepaBatchGroup.batch_id)
                .join(SepaBatchGroup, SepaDebit.group_id == SepaBatchGroup.id)
                .where(or_(SepaDebit.payment_id.in_(payment_ids),
                           SepaDebit.return_payment_id.in_(payment_ids)))):
            for payment_id in (debit.payment_id, debit.return_payment_id):
                if payment_id:
                    batches[payment_id] = batch_id
    for payment in payments:
        for allocation in payment.allocations:
            if allocation.charge_id in movements:
                movements[allocation.charge_id].append((payment, allocation))
    states = {}
    for charge in charges:
        balance = balances[charge.id]
        if charge.lifecycle == 'void':
            state = ('Anulado', 'text-bg-secondary')
        elif charge.lifecycle == 'draft':
            state = ('Borrador · no exigible', 'text-bg-secondary')
        elif charge.direction == 'credit':
            state = ('Corrección / abono', 'text-bg-secondary')
        elif balance.outstanding_amount == 0:
            state = ('✓ Cobrado', 'text-bg-success')
        elif balance.allocated_amount > 0:
            state = ('Parcial', 'text-bg-warning')
        elif balance.overdue:
            state = ('! Vencido', 'text-bg-danger')
        elif charge.due_date > today:
            state = ('Previsto futuro', 'text-bg-secondary')
        else:
            state = ('Pendiente', 'text-bg-warning')
        returned = any(p.lifecycle == 'posted' and p.direction == 'refund'
                       and p.method == 'sepa_direct_debit' for p, _ in movements[charge.id])
        states[charge.id] = dict(label=state[0], css=state[1], returned=returned,
            reopened=returned and charge.lifecycle == 'posted' and balance.outstanding_amount > 0)
    outstanding = [c for c in charges if c.lifecycle == 'posted' and c.direction == 'debit'
                   and balances[c.id].outstanding_amount > 0]
    future = [c for c in outstanding if c.due_date > today]
    return dict(movements=movements, batches=batches, states=states,
        future=sum((balances[c.id].outstanding_amount for c in future), Decimal('0.00')),
        due_today=sum((balances[c.id].outstanding_amount for c in outstanding
                       if c.due_date == today), Decimal('0.00')),
        next_due=min((c.due_date for c in future), default=None),
        planned=sum((balances[c.id].original_amount for c in charges if c.lifecycle != 'void'), Decimal('0.00')),
        deposit=sum((c.amount for c in charges if c.lifecycle != 'void' and c.type == 'security_deposit'), Decimal('0.00')))


def movement_label(payment):
    if payment.direction == 'refund':
        return 'Devolución SEPA' if payment.method == 'sepa_direct_debit' else 'Devolución de pago'
    return {'cash': 'Pago en efectivo', 'bank_transfer': 'Transferencia',
            'sepa_direct_debit': 'Cobro SEPA', 'card_or_platform': 'Pago por plataforma/tarjeta',
            'other': 'Otro cobro'}.get(payment.method, 'Cobro')
