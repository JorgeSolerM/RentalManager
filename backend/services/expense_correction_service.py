"""Administrative revisions, separate from actual payments and bank returns."""
from datetime import datetime, timezone
from sqlalchemy import select
from backend.models.owner_settlement import Expense, ExpensePayment, ExpenseCategory, OwnerSettlementLine
from backend.models.expense_correction import ExpensePaymentVoidOperation, ExpenseCorrectionOperation
from backend.services.expense_service import ExpenseService, fingerprint, request_id
from backend.services.financial_transaction import financial_transaction
from backend.services.settlement_money import money, percentage_fee, ZERO


def record(obj):
    return {c.name: getattr(obj, c.name) if isinstance(getattr(obj, c.name), (dict, list, bool))
            else None if getattr(obj, c.name) is None else str(getattr(obj, c.name)) for c in obj.__table__.columns}


class ExpenseCorrectionService:
    expenses = ExpenseService()

    def history(self, db, expense_id):
        result = []
        for model in (ExpensePaymentVoidOperation, ExpenseCorrectionOperation):
            for row in db.scalars(select(model).where(model.expense_id == expense_id)):
                result.append(dict(operation=row, kind='payment_void' if isinstance(row, ExpensePaymentVoidOperation) else row.kind))
        return sorted(result, key=lambda row: (row['operation'].created_at, row['operation'].request_key))

    def form(self, db, expense_id, kind, payment_id=None):
        if kind not in ('payment_void', 'correct', 'void'):
            raise ValueError('Operación no válida.')
        expense = db.get(Expense, expense_id)
        if expense is None:
            raise LookupError('Gasto no encontrado.')
        payments = self.expenses.payments(db, expense_id)
        payment = None
        if kind == 'payment_void':
            payment = db.get(ExpensePayment, payment_id)
            if payment is None or payment.expense_id != expense_id:
                raise LookupError('Pago no encontrado en este gasto.')
        ids = [p.id for p in payments]
        lines = list(db.scalars(select(OwnerSettlementLine).where(OwnerSettlementLine.expense_payment_id.in_(ids)))) if ids else []
        blockers = []
        if expense.lifecycle != 'posted':
            blockers.append('El gasto ya está anulado. Consulte el historial.')
        relevant = [line for line in lines if payment is None or line.expense_payment_id == payment.id]
        if relevant:
            blockers.append('Movimiento consumido en una liquidación cerrada, incluso de otro copropietario. Requiere regularización independiente; el cierre no se modifica.')
        if payment is not None:
            if payment.lifecycle != 'posted' or payment.direction != 'payment':
                blockers.append('Solo se anulan pagos vigentes registrados por error; no devoluciones ni pagos ya anulados.')
            if any(p.corrects_id == payment.id for p in payments):
                blockers.append('El pago tiene devoluciones o movimientos vinculados. Revise la cadena completa antes de regularizar.')
        else:
            if any(p.direction == 'reversal' or p.corrects_id for p in payments):
                blockers.append('Existen devoluciones o movimientos relacionados. El saldo neto cero no autoriza esta operación; requiere revisión específica.')
            for p in payments:
                if p.lifecycle == 'void':
                    audit = db.scalar(select(ExpensePaymentVoidOperation).where(ExpensePaymentVoidOperation.payment_id == p.id))
                    if audit is None or audit.after_state != record(p) or not audit.no_money_moved:
                        blockers.append('Existe un pago anulado sin auditoría íntegra. Revise su historial.')
            if kind == 'void' and any(p.lifecycle == 'posted' for p in payments):
                blockers.append('No se puede anular el gasto: existen pagos efectivos. Revise y anule primero los pagos únicamente si se registraron por error sin salida real de dinero.')
        try:
            balance = self.expenses.balance(db, expense_id)
        except ValueError:
            balance = None
            blockers.append('Los saldos no son coherentes. Requiere revisión de integridad económica.')
        return dict(expense=expense, payment=payment, payments=payments, lines=lines, balance=balance,
                    blockers=list(dict.fromkeys(blockers)), history=self.history(db, expense_id), kind=kind)

    def normalized(self, kind, reason, base_amount=None, concept=None, category_id=None, no_money_moved=False):
        reason = (reason or '').strip()
        if not reason or len(reason) > 1000:
            raise ValueError('Indique un motivo obligatorio de hasta 1000 caracteres.')
        if kind not in ('payment_void', 'correct', 'void'):
            raise ValueError('Operación no válida.')
        result = dict(kind=kind, reason=reason)
        if kind == 'payment_void':
            if no_money_moved is not True:
                raise ValueError('Confirme que el pago se registró por error y no hubo salida real de dinero. Si se pagó realmente, utilice devolución real o regularización.')
            result['no_money_moved'] = True
        elif kind == 'correct':
            try:
                category_id = int(category_id)
            except (ValueError, TypeError):
                raise ValueError('Seleccione una categoría válida.') from None
            concept = (concept or '').strip()
            if not concept or len(concept) > 255:
                raise ValueError('Indique un concepto de hasta 255 caracteres.')
            result.update(base_amount=str(money(base_amount)), concept=concept, category_id=category_id)
        return result

    def preview(self, db, expense_id, *, payment_id=None, **values):
        values = self.normalized(**values)
        view = self.form(db, expense_id, values['kind'], payment_id)
        if view['blockers']:
            raise ValueError(' '.join(view['blockers']))
        expense, balance = view['expense'], view['balance']
        before = record(view['payment'] or expense)
        after = before.copy()
        if values['kind'] == 'correct':
            category = db.get(ExpenseCategory, values['category_id'])
            if category is None or (not category.active and category.id != expense.category_id):
                raise ValueError('No se puede seleccionar una categoría inactiva.')
            base = money(values['base_amount'])
            tax, retained = percentage_fee(base, expense.vat_rate), percentage_fee(base, expense.withholding_rate)
            total = money(base + tax - retained)
            if total <= ZERO or total < balance.paid:
                raise ValueError('El total debe ser positivo y no puede quedar por debajo del importe efectivamente pagado.')
            after.update(base_amount=str(base), vat_amount=str(tax), withholding_amount=str(retained), total_amount=str(total),
                         concept=values['concept'], category_id=str(category.id))
            if after == before:
                raise ValueError('No hay cambios que registrar.')
            paid, unpaid, available = balance.paid, total-balance.paid, balance.available
        elif values['kind'] == 'payment_void':
            after['lifecycle'] = 'void'
            paid = balance.paid-view['payment'].amount
            if paid < ZERO:
                raise ValueError('La anulación produciría un saldo negativo. Revise los movimientos.')
            total, unpaid, available = balance.total, balance.total-paid, paid-balance.settled
        else:
            after['lifecycle'] = 'void'
            total, paid, unpaid, available = balance.total, ZERO, ZERO, ZERO
        impact = dict(total_before=str(balance.total), total_after=str(total), paid_before=str(balance.paid), paid_after=str(paid),
                      unpaid_before=str(balance.unpaid), unpaid_after=str(unpaid), available_before=str(balance.available), available_after=str(available))
        state = dict(expense=record(expense), payments=[record(p) for p in view['payments']], lines=[record(l) for l in view['lines']],
                     history=[record(h['operation']) for h in view['history']], values=values, payment_id=payment_id, after=after)
        return dict(**view, before=before, after=after, impact=impact, values=values, fingerprint=fingerprint(state))

    def confirm(self, db, expense_id, *, payment_id=None, request_key, expected, confirmed=False, **values):
        if confirmed is not True:
            raise ValueError('Confirme expresamente la operación revisada.')
        values = self.normalized(**values)
        key = request_id(request_key)
        digest = fingerprint([expense_id, payment_id, values])
        model = ExpensePaymentVoidOperation if values['kind'] == 'payment_void' else ExpenseCorrectionOperation
        with financial_transaction(db):
            for existing_model in (ExpensePaymentVoidOperation, ExpenseCorrectionOperation):
                prior = db.get(existing_model, key)
                if prior:
                    if existing_model != model or prior.fingerprint != digest:
                        raise ValueError('Esta solicitud ya se utilizó con otros datos.')
                    return prior
            view = self.preview(db, expense_id, payment_id=payment_id, **values)
            if view['fingerprint'] != expected:
                raise ValueError('Los datos han cambiado. Revise nuevamente la operación.')
            target = view['payment'] or view['expense']
            if values['kind'] == 'correct':
                for name in ('base_amount', 'vat_amount', 'withholding_amount', 'total_amount'):
                    setattr(target, name, money(view['after'][name]))
                target.concept, target.category_id = values['concept'], values['category_id']
            else:
                target.lifecycle = 'void'
                target.voided_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.flush()
            extra = dict(payment_id=payment_id, no_money_moved=True) if model is ExpensePaymentVoidOperation else dict(kind=values['kind'])
            operation = model(request_key=key, expense_id=expense_id, reason=values['reason'], before_state=view['before'],
                after_state=record(target), impact=view['impact'], fingerprint=digest, reviewed_state=expected, **extra)
            db.add(operation)
        return operation
