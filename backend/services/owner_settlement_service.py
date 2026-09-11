"""Individual owner settlements; previews never write and closes serialize."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from backend.core.business_time import business_today
from backend.models.booking import Booking
from backend.models.booking_charge import BookingCharge
from backend.models.payment import Payment
from backend.models.payment_allocation import PaymentAllocation
from backend.models.owner import Owner
from backend.models.owner_bank_account import OwnerBankAccount
from backend.models.property_ownership import PropertyOwnership
from backend.models.room import Room
from backend.models.sepa_collection import SepaDebit
from backend.models.owner_settlement import (
    Expense, ExpensePayment, ManagementFeeTerms, OwnerPayout, OwnerSettlement,
    OwnerSettlementLine, PaymentCustody, SettlementChargePolicy,
)
from backend.services.expense_service import fingerprint, request_id
from backend.services.financial_transaction import financial_transaction
from backend.services.settlement_money import ZERO, money, percentage_fee, split_money, distribute_custody, settlement_totals


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def serial(value):
    if isinstance(value, dict):
        return {str(k): serial(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serial(v) for v in value]
    if isinstance(value, (Decimal, date)):
        return str(value)
    return value


class OwnerSettlementService:
    def version_ownership(self, db, property_id, effective_from, shares):
        shares = [(int(owner), money(percentage)) for owner, percentage in shares]
        split_money("1", shares)
        if effective_from > business_today():
            raise ValueError("Aplique la titularidad cuando entre en vigor; no se adelanta el estado activo de otras pantallas.")
        with financial_transaction(db):
            current = list(db.scalars(select(PropertyOwnership).where(
                PropertyOwnership.property_id == property_id, PropertyOwnership.active == True)))
            if not current or any(r.effective_from and r.effective_from >= effective_from for r in current):
                raise ValueError("La fecha debe ser posterior al inicio de la titularidad actual.")
            used = list(db.scalars(select(OwnerSettlementLine).where(OwnerSettlementLine.property_id == property_id)))
            for row in used:
                economic_end = row.snapshot.get("economic_end")
                if economic_end and economic_end > str(effective_from):
                    raise ValueError("El cambio afectaría a periodos ya liquidados.")
                if row.kind == "expense":
                    payment = db.get(ExpensePayment, row.expense_payment_id)
                    if db.get(Expense, payment.expense_id).expense_date >= effective_from:
                        raise ValueError("El cambio afectaría a gastos ya liquidados.")
            accounts = {r.owner_id: r.rent_bank_account_id for r in current}
            for row in current:
                row.active = False
                row.effective_until = effective_from - timedelta(days=1)
            db.flush()
            for owner_id, percentage in shares:
                if db.get(Owner, owner_id) is None:
                    raise ValueError("Propietario no encontrado.")
                db.add(PropertyOwnership(property_id=property_id, owner_id=owner_id,
                    ownership_percentage=percentage, effective_from=effective_from, active=True,
                    rent_bank_account_id=accounts.get(owner_id)))

    def ownership(self, db, property_id, start, end=None):
        if start is None:
            raise ValueError("El cargo no tiene periodo económico; debe revisarse antes de liquidar.")
        end = end or start + timedelta(days=1)
        # Legacy effective_until is inclusive. A change within a charge is not
        # silently assigned to its first day: the preview reports ambiguity.
        rows = list(db.scalars(select(PropertyOwnership).where(PropertyOwnership.property_id == property_id)))
        overlapping = [r for r in rows if (r.active or r.effective_until is not None)
                       and (r.effective_from is None or r.effective_from < end)
                       and (r.effective_until is None or r.effective_until >= start)]
        if any((r.effective_from and r.effective_from > start) or
               (r.effective_until and r.effective_until < end - timedelta(days=1)) for r in overlapping):
            raise ValueError("Cambio de titularidad dentro del periodo económico: revise la atribución.")
        split_money("1", [(r.owner_id, r.ownership_percentage) for r in overlapping])
        return overlapping

    def fee_terms(self, db, property_id, owner_id, start, end):
        rows = list(db.scalars(select(ManagementFeeTerms).where(
            ManagementFeeTerms.property_id == property_id, ManagementFeeTerms.owner_id == owner_id)))
        overlaps = [r for r in rows if r.effective_from < end and (r.effective_until is None or r.effective_until > start)]
        if len(overlaps) != 1 or overlaps[0].effective_from > start or (overlaps[0].effective_until and overlaps[0].effective_until < end):
            raise ValueError("Faltan condiciones de honorarios inequívocas para el periodo económico.")
        return overlaps[0]

    def add_terms(self, db, *, property_id, owner_id, effective_from, effective_until,
                  percentage, vat_rate, withholding_rate):
        values = [money(v) for v in (percentage, vat_rate, withholding_rate)]
        if any(v > 100 for v in values) or effective_from.day != 1 or (effective_until and (effective_until.day != 1 or effective_until <= effective_from)):
            raise ValueError("Tipos de 0 a 100 y vigencia por meses completos; fin exclusivo.")
        with financial_transaction(db):
            applicable = self.ownership(db, property_id, effective_from)
            if owner_id not in {r.owner_id for r in applicable}:
                raise ValueError("El propietario no participa en esa finca durante la vigencia indicada.")
            if db.get(Owner, owner_id) is None:
                raise ValueError("Propietario no encontrado.")
            existing = list(db.scalars(select(ManagementFeeTerms).where(ManagementFeeTerms.property_id == property_id, ManagementFeeTerms.owner_id == owner_id)))
            overlaps = [r for r in existing if r.effective_from < (effective_until or date.max) and (r.effective_until or date.max) > effective_from]
            if overlaps:
                if len(overlaps) != 1 or overlaps[0].effective_until is not None or overlaps[0].effective_from >= effective_from:
                    raise ValueError("Las versiones no pueden solaparse.")
                previous = overlaps[0]
                used = list(db.scalars(select(OwnerSettlementLine).where(OwnerSettlementLine.fee_terms_id == previous.id)))
                if any(r.snapshot.get("economic_end", "9999-12-31") > str(effective_from) for r in used):
                    raise ValueError("La nueva vigencia alteraría periodos ya liquidados.")
                previous.effective_until = effective_from
            terms = ManagementFeeTerms(property_id=property_id, owner_id=owner_id,
                effective_from=effective_from, effective_until=effective_until,
                percentage=values[0], vat_rate=values[1], withholding_rate=values[2])
            db.add(terms)
        return terms

    def set_custody(self, db, payment_id, *, actor, owner_id=None):
        if actor not in {"manager", "owner"} or (actor == "owner") != (owner_id is not None):
            raise ValueError("Identifique quién recibió el cobro.")
        with financial_transaction(db):
            payment = db.get(Payment, payment_id)
            if payment is None or payment.direction != "receipt" or payment.lifecycle != "posted":
                raise ValueError("Cobro no disponible.")
            if db.scalar(select(SepaDebit.id).where(SepaDebit.payment_id == payment_id)):
                raise ValueError("La cuenta receptora SEPA determina la custodia; no se sustituye manualmente.")
            if db.scalar(select(OwnerSettlementLine.id).join(PaymentAllocation,
                    OwnerSettlementLine.payment_allocation_id == PaymentAllocation.id).where(PaymentAllocation.payment_id == payment_id)):
                raise ValueError("La custodia ya está congelada en una liquidación.")
            if owner_id and db.get(Owner, owner_id) is None:
                raise ValueError("Propietario no encontrado.")
            old = list(db.scalars(select(PaymentCustody).where(PaymentCustody.payment_id == payment_id)))
            for row in old:
                db.delete(row)
            db.add(PaymentCustody(payment_id=payment_id, actor=actor, owner_id=owner_id, amount=payment.amount))

    def _receipts(self, db, payment, allocation):
        rows = list(db.scalars(select(PaymentCustody).where(PaymentCustody.payment_id == payment.id).order_by(PaymentCustody.id)))
        if not rows:
            debit = db.scalar(select(SepaDebit).where(SepaDebit.payment_id == payment.id).options(joinedload(SepaDebit.group)))
            if not debit:
                raise ValueError("Cobro sin custodia identificada; registre quién recibió el dinero.")
            account = db.get(OwnerBankAccount, debit.group.bank_account_id)
            if account is None or account.iban != debit.group.snapshot.get("creditor_iban"):
                raise ValueError("La cuenta SEPA histórica requiere revisión de custodia.")
            return [(account.owner_id, allocation.amount)]
        if sum((r.amount for r in rows), ZERO) != payment.amount:
            raise ValueError("Custodia incompleta.")
        if len(rows) == 1:
            return [(rows[0].owner_id, allocation.amount)]
        # Explicit multi-recipient imports need per-allocation attribution.
        # Multiple receipts for a booking can instead use separate Payments.
        raise ValueError("Custodia múltiple en un Payment: se requiere atribución por cargo.")

    def _income_distribution(self, db, allocation, all_lines):
        key = f"income:{allocation.id}"
        frozen = next((l.snapshot["distribution"] for l in all_lines if l.source_key == key), None)
        if frozen is not None:
            return frozen
        payment, charge = allocation.payment, allocation.charge
        if payment.currency != "EUR" or charge.currency != "EUR":
            raise ValueError("Esta fase solo admite importes en EUR.")
        if payment.direction == "refund":
            original = db.scalar(select(PaymentAllocation).where(
                PaymentAllocation.payment_id == payment.corrects_payment_id, PaymentAllocation.charge_id == charge.id)
                .options(joinedload(PaymentAllocation.payment), joinedload(PaymentAllocation.charge)))
            if original is None:
                raise ValueError("Devolución sin allocation original identificable.")
            distribution = self._income_distribution(db, original, all_lines)
            earlier = sum(db.scalars(select(PaymentAllocation.amount).join(Payment).where(
                Payment.corrects_payment_id == payment.corrects_payment_id, Payment.direction == "refund",
                Payment.lifecycle == "posted", PaymentAllocation.charge_id == charge.id,
                PaymentAllocation.id < allocation.id)), ZERO)
            if earlier + allocation.amount > original.amount:
                raise ValueError("Las devoluciones superan el importe original asignado.")
            def reverse(value):
                value = Decimal(value)
                before = (value * earlier / original.amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                after = (value * (earlier + allocation.amount) / original.amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                return str(before - after)
            return {owner: {**row, **{k: reverse(row[k]) for k in
                    ("amount", "fee", "fee_base", "fee_vat", "fee_withholding", "direct", "manager", "difference")},
                    "reversal_of": f"income:{original.id}"} for owner, row in distribution.items()}
        policy = db.get(SettlementChargePolicy, charge.type)
        liquidable = policy.liquidable_to_owner if policy else charge.type == "rent"
        fee_base = policy.included_in_management_fee_base if policy else charge.type == "rent"
        if not liquidable and not fee_base:
            return {}
        booking = db.get(Booking, charge.booking_id)
        room = db.get(Room, booking.room_id)
        start, end = charge.service_period_start, charge.service_period_end
        ownerships = self.ownership(db, room.property_id, start, end)
        shares = [(r.owner_id, r.ownership_percentage) for r in ownerships]
        custody = distribute_custody(allocation.amount, shares, self._receipts(db, payment, allocation))
        result = {}
        for relation in ownerships:
            row = custody[relation.owner_id]
            terms = self.fee_terms(db, room.property_id, relation.owner_id, start, end or start + timedelta(days=1)) if fee_base else None
            base = percentage_fee(row.economic_income, terms.percentage) if terms else ZERO
            vat = percentage_fee(base, terms.vat_rate) if terms else ZERO
            withheld = percentage_fee(base, terms.withholding_rate) if terms else ZERO
            result[str(relation.owner_id)] = serial(dict(amount=row.economic_income if liquidable else ZERO,
                fee=base + vat - withheld, fee_base=base, fee_vat=vat, fee_withholding=withheld,
                direct=row.directly_received if liquidable else ZERO, manager=row.manager_held_funds if liquidable else ZERO,
                difference=row.inter_owner_difference if liquidable else ZERO,
                ownership_id=relation.id, percentage=relation.ownership_percentage,
                fee_terms_id=terms.id if terms else None, fee_percentage=terms.percentage if terms else ZERO,
                property_id=room.property_id, room=room.code, concept=charge.concept,
                economic_start=start, economic_end=end))
        return result

    def _expense_distribution(self, db, payment, all_lines):
        key = f"expense:{payment.id}"
        frozen = next((l.snapshot["distribution"] for l in all_lines if l.source_key == key), None)
        if frozen is not None:
            return frozen
        if payment.direction == "reversal":
            original = db.get(ExpensePayment, payment.corrects_id)
            source = self._expense_distribution(db, original, all_lines)
            # Preserve original attribution; partial reversals use cents and
            # original percentages, never current ownership.
            shares = [(int(owner), row["percentage"]) for owner, row in source.items()]
            amounts = split_money(-payment.amount, shares)
            return {owner: {**row, "amount": str(amounts[int(owner)]),
                    "manager": str(amounts[int(owner)] if original.paid_by == "manager" else ZERO),
                    "reversal_of": f"expense:{original.id}"} for owner, row in source.items()}
        expense = db.get(Expense, payment.expense_id)
        if expense.borne_by != "owner" or expense.lifecycle != "posted":
            return {}
        if payment.paid_by == "other":
            raise ValueError("Gasto pagado por tercero: custodia pendiente de identificar.")
        relations = self.ownership(db, expense.property_id, expense.expense_date) if not expense.owner_id else []
        shares = [(r.owner_id, r.ownership_percentage) for r in relations] if relations else [(expense.owner_id, Decimal("100"))]
        amounts = split_money(payment.amount, shares)
        return {str(owner): serial(dict(amount=value, manager=value if payment.paid_by == "manager" else ZERO,
                property_id=expense.property_id, concept=expense.concept, paid_by=payment.paid_by,
                paid_by_owner_id=payment.paid_by_owner_id, percentage=dict(shares)[owner],
                ownership_id=next((r.id for r in relations if r.owner_id == owner), None))) for owner, value in amounts.items()}

    def preview(self, db, owner_id, start, end, property_ids, excluded=()):
        if start >= end or not property_ids or db.get(Owner, owner_id) is None:
            raise ValueError("Revise propietario, periodo y fincas.")
        property_ids = sorted(set(int(v) for v in property_ids))
        all_lines = list(db.scalars(select(OwnerSettlementLine)))
        consumed = {l.source_key for l in all_lines if l.owner_id == owner_id}
        rows, errors = [], []
        allocations = list(db.scalars(select(PaymentAllocation).join(Payment).join(BookingCharge,
            PaymentAllocation.charge_id == BookingCharge.id).join(Booking, BookingCharge.booking_id == Booking.id)
            .join(Room, Booking.room_id == Room.id).where(Room.property_id.in_(property_ids),
            Payment.lifecycle == "posted", Payment.effective_date < end, BookingCharge.lifecycle == "posted")
            .options(joinedload(PaymentAllocation.payment), joinedload(PaymentAllocation.charge)).order_by(PaymentAllocation.id)))
        expenses = list(db.scalars(select(ExpensePayment).join(Expense).where(
            Expense.property_id.in_(property_ids), ExpensePayment.effective_date < end).order_by(ExpensePayment.id)))
        for kind, sources, builder in (("income", allocations, self._income_distribution), ("expense", expenses, self._expense_distribution)):
            for source in sources:
                key = f"{kind}:{source.id}"
                if key in consumed:
                    continue
                try:
                    distribution = builder(db, source, all_lines)
                    row = distribution.get(str(owner_id))
                    if not row:
                        continue
                    rows.append(dict(key=key, kind=kind, source_id=source.id, **row,
                                     distribution=distribution, included=key not in excluded,
                                     date=str(source.payment.effective_date if kind == "income" else source.effective_date)))
                except ValueError as exc:
                    errors.append(f"{key}: {exc}")
        previous = list(db.scalars(select(OwnerSettlement).where(OwnerSettlement.owner_id == owner_id,
            OwnerSettlement.status == "closed", OwnerSettlement.period_end <= end).order_by(OwnerSettlement.id)))
        for old in previous:
            carry = Decimal(old.snapshot["totals"]["carry_forward"])
            key = f"prior_balance:{old.id}"
            if carry < ZERO and key not in consumed:
                rows.append(dict(key=key, kind="prior_balance", source_id=old.id, amount=str(carry),
                    concept=f"Compensación de saldo de liquidación {old.id}", included=True, date=str(old.period_end),
                    origin_settlement_id=old.id))
        included = {r["key"] for r in rows if r["included"]}
        for row in rows:
            original = row.get("reversal_of")
            if original and original not in consumed and ((original in included) != row["included"]):
                errors.append("Un cobro/pago y su devolución pendiente deben revisarse conjuntamente.")
        def total(kind, field):
            return sum((Decimal(r.get(field, "0")) for r in rows if r["included"] and r["kind"] == kind), ZERO)
        totals = settlement_totals(income=total("income", "amount"), expenses=total("expense", "amount"),
            fees=total("income", "fee"), manager_receipts=total("income", "manager"),
            manager_expenses=total("expense", "manager"), adjustments=total("prior_balance", "amount"),
            funds_adjustments=total("prior_balance", "amount"))
        summary = {**serial(asdict(totals)), "income": str(total("income", "amount")),
            "expenses": str(total("expense", "amount")), "fees": str(total("income", "fee")),
            "directly_received": str(total("income", "direct")), "manager_held_funds": str(total("income", "manager")),
            "inter_owner_difference": str(total("income", "difference")), "prior_balance": str(total("prior_balance", "amount"))}
        payload = dict(owner_id=owner_id, start=str(start), end=str(end), property_ids=property_ids,
                       excluded=sorted(excluded), rows=rows, errors=errors, totals=summary)
        return {**payload, "fingerprint": fingerprint(payload)}

    def save_draft(self, db, *, owner_id, start, end, property_ids, excluded, expected, request_key):
        key = request_id(request_key)
        with financial_transaction(db):
            previous = db.scalar(select(OwnerSettlement).where(OwnerSettlement.request_key == key))
            if previous:
                if previous.fingerprint != expected:
                    raise ValueError("Solicitud ya utilizada con otros datos.")
                return previous
            preview = self.preview(db, owner_id, start, end, property_ids, excluded)
            if preview["fingerprint"] != expected:
                raise ValueError("Los datos han cambiado. Revise nuevamente la liquidación.")
            draft = OwnerSettlement(owner_id=owner_id, period_start=start, period_end=end,
                selection={"properties": property_ids, "excluded": excluded}, fingerprint=expected,
                snapshot=preview, request_key=key, status="draft")
            db.add(draft)
        return draft

    def close(self, db, settlement_id, expected):
        with financial_transaction(db):
            draft = db.get(OwnerSettlement, settlement_id)
            if draft is None:
                raise ValueError("Liquidación no encontrada.")
            if draft.fingerprint != expected:
                raise ValueError("Versión del borrador incorrecta.")
            if draft.status == "closed":
                return draft
            if draft.status != "draft":
                raise ValueError("La liquidación no está en borrador.")
            preview = self.preview(db, draft.owner_id, draft.period_start, draft.period_end,
                                   draft.selection["properties"], draft.selection["excluded"])
            if preview["fingerprint"] != expected:
                raise ValueError("Datos desactualizados. Cree un nuevo borrador tras revisar los cambios.")
            if preview["errors"]:
                raise ValueError("Resuelva las incidencias de atribución antes de cerrar.")
            if not any(r["included"] for r in preview["rows"]):
                raise ValueError("No hay movimientos seleccionados.")
            for row in preview["rows"]:
                if not row["included"]:
                    continue
                source = {"income": "payment_allocation_id", "expense": "expense_payment_id", "prior_balance": "prior_settlement_id"}[row["kind"]]
                db.add(OwnerSettlementLine(settlement_id=draft.id, owner_id=draft.owner_id,
                    kind=row["kind"], source_key=row["key"], property_id=row.get("property_id"),
                    amount=Decimal(row["amount"]), fee_amount=Decimal(row.get("fee", "0")),
                    ownership_id=row.get("ownership_id"), fee_terms_id=row.get("fee_terms_id"),
                    snapshot=row, **{source: row["source_id"]}))
            from backend.services.settlement_document_service import document_identity
            preview['document_identity'] = document_identity(db, draft, [r for r in preview['rows'] if r['included']])
            draft.status, draft.closed_at, draft.snapshot = "closed", now(), preview
        return draft

    def payout(self, db, settlement_id, *, amount, effective_date, bank_account_id, method,
               request_key, reference=None, notes=None):
        amount, key = money(amount), request_id(request_key)
        if amount <= ZERO or effective_date > business_today() or method not in {"bank_transfer", "other"}:
            raise ValueError("Revise importe, método y fecha efectiva.")
        digest = fingerprint([settlement_id, amount, effective_date, bank_account_id, method, reference, notes])
        with financial_transaction(db):
            previous = db.scalar(select(OwnerPayout).where(OwnerPayout.request_key == key))
            if previous:
                if previous.fingerprint != digest:
                    raise ValueError("Solicitud ya utilizada con otros datos.")
                return previous
            settlement = db.get(OwnerSettlement, settlement_id)
            account = db.get(OwnerBankAccount, bank_account_id)
            if settlement is None or settlement.status != "closed":
                raise ValueError("Cierre la liquidación antes de registrar un pago.")
            if account is None or account.owner_id != settlement.owner_id or not account.active or not account.receives_settlements:
                raise ValueError("Cuenta destino no válida para este propietario.")
            paid = sum(db.scalars(select(OwnerPayout.amount).where(OwnerPayout.settlement_id == settlement_id)), ZERO)
            if amount > Decimal(settlement.snapshot["totals"]["payout_due"]) - paid:
                raise ValueError("El pago supera los fondos pendientes de transferir.")
            owner_lines = list(db.scalars(select(OwnerSettlementLine).where(OwnerSettlementLine.owner_id == settlement.owner_id)))
            consumed = {r.payment_allocation_id for r in owner_lines if r.payment_allocation_id}
            original_payments = list(db.scalars(select(PaymentAllocation.payment_id).where(PaymentAllocation.id.in_(consumed))))
            pending_returns = list(db.scalars(select(PaymentAllocation.id).join(Payment).where(
                Payment.corrects_payment_id.in_(original_payments), Payment.lifecycle == "posted",
                Payment.direction == "refund", PaymentAllocation.id.not_in(consumed))))
            if pending_returns:
                raise ValueError("Hay devoluciones pendientes de liquidar; revise el ajuste antes de transferir fondos.")
            closed = list(db.scalars(select(OwnerSettlement).where(OwnerSettlement.owner_id == settlement.owner_id,
                                                                   OwnerSettlement.status == "closed")))
            # Carry rows transfer an existing negative balance; do not count it twice.
            owner_funds = sum((Decimal(s.snapshot["totals"]["funds_balance"]) -
                               Decimal(s.snapshot["totals"]["prior_balance"]) for s in closed), ZERO)
            owner_paid = sum(db.scalars(select(OwnerPayout.amount).where(OwnerPayout.owner_id == settlement.owner_id)), ZERO)
            if amount > max(ZERO, owner_funds - owner_paid):
                raise ValueError("El pago supera los fondos netos del propietario tras los ajustes cerrados.")
            payout = OwnerPayout(settlement_id=settlement_id, owner_id=settlement.owner_id,
                amount=amount, effective_date=effective_date, bank_account_id=account.id,
                account_snapshot={"holder": account.account_holder_name, "iban": account.iban, "bic": account.bic},
                method=method, reference=reference, notes=notes, request_key=key, fingerprint=digest)
            db.add(payout)
        return payout
