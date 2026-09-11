"""Cash-basis expenses. Registration never manufactures a payment."""
from datetime import date
from hashlib import sha256
import json
from uuid import UUID

from sqlalchemy import select

from backend.core.business_time import business_today
from backend.models.owner import Owner
from backend.models.provider import Provider
from backend.models.property import Property
from backend.models.owner_settlement import Expense, ExpenseCategory, ExpensePayment, OwnerSettlementLine
from backend.services.financial_transaction import financial_transaction
from backend.services.settlement_money import ZERO, expense_balance, money, percentage_fee


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=True).encode()).hexdigest()


def request_id(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Identificador de solicitud no válido.") from None


class ExpenseService:
    def list(self, db):
        return list(db.scalars(select(Expense).order_by(Expense.expense_date.desc(), Expense.id.desc())))

    def payments(self, db, expense_id):
        return list(db.scalars(select(ExpensePayment).where(ExpensePayment.expense_id == expense_id)
                               .order_by(ExpensePayment.effective_date, ExpensePayment.id)))

    def balance(self, db, expense_id):
        expense = db.get(Expense, expense_id)
        if expense is None:
            raise ValueError("Gasto no encontrado.")
        payments = self.payments(db, expense_id)
        ids = [p.id for p in payments]
        consumed = list(db.scalars(select(OwnerSettlementLine.amount).where(
            OwnerSettlementLine.expense_payment_id.in_(ids)))) if ids else []
        return expense_balance(expense.total_amount,
                               [p.amount if p.direction == "payment" else -p.amount for p in payments],
                               sum(consumed, ZERO))

    def create(self, db, *, property_id, category_id, expense_date, concept, base_amount,
               vat_rate, withholding_rate, owner_id=None, borne_by="owner", supplier=None, notes=None, provider_id=None):
        base, vat, withholding = map(money, (base_amount, vat_rate, withholding_rate))
        if max(vat, withholding) > 100:
            raise ValueError("Tipo fiscal fuera de rango.")
        tax, retained = percentage_fee(base, vat), percentage_fee(base, withholding)
        total = money(base + tax - retained)
        if total <= ZERO or borne_by not in {"owner", "manager", "tenant", "other"}:
            raise ValueError("Importe o responsable del gasto no válido.")
        concept = (concept or "").strip()
        if not concept or len(concept) > 255 or not isinstance(expense_date, date):
            raise ValueError("Revise el concepto y la fecha del gasto.")
        if supplier and len(supplier) > 180 or notes and len(notes) > 2000:
            raise ValueError("Proveedor o nota demasiado larga.")
        with financial_transaction(db):
            category = db.get(ExpenseCategory, category_id)
            if db.get(Property, property_id) is None or category is None or not category.active:
                raise ValueError("Finca o categoría no disponible.")
            if owner_id and db.get(Owner, owner_id) is None:
                raise ValueError("Propietario no encontrado.")
            if owner_id:
                from backend.services.owner_settlement_service import OwnerSettlementService
                if borne_by != 'owner' or owner_id not in {r.owner_id for r in OwnerSettlementService().ownership(db, property_id, expense_date)}:
                    raise ValueError('El propietario específico debe pertenecer a la finca en la fecha del gasto y soportar el gasto.')
            provider = db.get(Provider, provider_id) if provider_id else None
            if provider_id and (provider is None or not provider.active):
                raise ValueError('Proveedor no disponible para un gasto nuevo.')
            expense = Expense(property_id=property_id, category_id=category_id, owner_id=owner_id,
                expense_date=expense_date, concept=concept, base_amount=base, vat_rate=vat,
                vat_amount=tax, withholding_rate=withholding, withholding_amount=retained,
                total_amount=total, borne_by=borne_by, supplier=supplier, notes=notes, lifecycle="posted",
                provider_id=provider_id, provider_snapshot=provider.fiscal_snapshot() if provider else None)
            db.add(expense)
        return expense

    def pay(self, db, expense_id, *, effective_date, amount, paid_by, request_key,
            method="bank_transfer", paid_by_owner_id=None, reference=None, notes=None, corrects_id=None):
        amount = money(amount)
        key = request_id(request_key)
        if amount <= ZERO or effective_date > business_today():
            raise ValueError("El pago debe ser positivo y no futuro.")
        if paid_by not in {"manager", "owner", "other"} or method not in {"bank_transfer", "cash", "card", "other"}:
            raise ValueError("Revise quién pagó y el método.")
        if (paid_by == "owner") != (paid_by_owner_id is not None):
            raise ValueError("Identifique el propietario que realizó el pago.")
        if reference and len(reference) > 255 or notes and len(notes) > 2000:
            raise ValueError("Referencia o nota demasiado larga.")
        payload = [expense_id, effective_date, amount, paid_by, paid_by_owner_id, method, reference, notes, corrects_id]
        digest = fingerprint(payload)
        with financial_transaction(db):
            previous = db.scalar(select(ExpensePayment).where(ExpensePayment.request_key == key))
            if previous:
                if previous.fingerprint != digest:
                    raise ValueError("La solicitud ya se utilizó con otros datos.")
                return previous
            expense = db.get(Expense, expense_id)
            if expense is None or expense.lifecycle != "posted":
                raise ValueError("Gasto no disponible para pagos.")
            if paid_by_owner_id and db.get(Owner, paid_by_owner_id) is None:
                raise ValueError("Propietario no encontrado.")
            balance = self.balance(db, expense_id)
            if corrects_id:
                original = db.get(ExpensePayment, corrects_id)
                if (original is None or original.expense_id != expense_id or original.direction != "payment"
                        or original.paid_by != paid_by or original.paid_by_owner_id != paid_by_owner_id
                        or effective_date < original.effective_date):
                    raise ValueError("La corrección debe conservar el gasto y quién pagó originalmente.")
                returned = sum(db.scalars(select(ExpensePayment.amount).where(ExpensePayment.corrects_id == corrects_id)), ZERO)
                if amount > original.amount - returned or amount > balance.paid:
                    raise ValueError("La devolución supera el pago disponible.")
            elif amount > balance.unpaid:
                raise ValueError("El pago supera el importe pendiente del gasto.")
            payment = ExpensePayment(expense_id=expense_id, effective_date=effective_date, amount=amount,
                paid_by=paid_by, paid_by_owner_id=paid_by_owner_id, method=method, reference=reference,
                notes=notes, corrects_id=corrects_id, direction="reversal" if corrects_id else "payment",
                request_key=key, fingerprint=digest)
            db.add(payment)
        return payment
