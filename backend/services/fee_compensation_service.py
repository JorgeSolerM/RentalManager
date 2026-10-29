"""Explicit, append-only applications; caller's sources are never rewritten.

Not wired into production settlement closing until the new grouped workflow and
migration are validated. Every public write owns a serialized transaction.
"""
from datetime import date
from sqlalchemy import select

from backend.core.fee_compensation import Obligation, compensation_plan
from backend.models.fee_billing import FeeObligation, FeeObligationAdjustment, FeeFund, FeeCompensation, FeeCompensationRun
from backend.models.owner_settlement import OwnerSettlement, OwnerPayout
from backend.services.expense_service import fingerprint, request_id
from backend.services.financial_transaction import financial_transaction
from backend.services.settlement_money import ZERO, money


class FeeCompensationService:
    def balances(self, db, owner_id):
        obligations = list(db.scalars(select(FeeObligation).where(FeeObligation.owner_id == owner_id)))
        ids = [r.id for r in obligations]
        adjustments = list(db.scalars(select(FeeObligationAdjustment).where(FeeObligationAdjustment.obligation_id.in_(ids))))
        applications = list(db.scalars(select(FeeCompensation).where(FeeCompensation.obligation_id.in_(ids))))
        result = []
        for item in obligations:
            generated = item.amount + sum((r.amount for r in adjustments if r.obligation_id == item.id), ZERO)
            compensated = sum((r.amount if r.direction == 'application' else -r.amount
                               for r in applications if r.obligation_id == item.id), ZERO)
            if not ZERO <= compensated <= generated:
                raise ValueError('La obligación necesita una corrección trazada antes de compensarse.')
            result.append(Obligation(str(item.id), owner_id, item.kind, item.effective_date,
                                     generated, compensated))
        return result

    def fund_available(self, db, fund):
        applications = list(db.scalars(select(FeeCompensation).where(FeeCompensation.fund_id == fund.id)))
        consumed = sum((r.amount if r.direction == 'application' else -r.amount for r in applications), ZERO)
        if not ZERO <= consumed <= fund.amount:
            raise ValueError('Fondos con aplicaciones incoherentes.')
        return fund.amount - consumed

    def apply(self, db, *, fund_id, settlement_id, effective_date, request_key):
        key = request_id(request_key)
        if type(effective_date) is not date:
            raise ValueError('Fecha efectiva no válida.')
        digest = fingerprint([fund_id, settlement_id, str(effective_date)])
        with financial_transaction(db):
            fund = db.get(FeeFund, fund_id)
            settlement = db.get(OwnerSettlement, settlement_id)
            if (fund is None or settlement is None or fund.owner_id != settlement.owner_id
                    or fund.settlement_id != settlement_id or settlement.status != 'closed'):
                raise ValueError('Fondos y liquidación cerrada deben pertenecer al mismo propietario y origen.')
            if settlement.selection.get('billing'):
                raise ValueError('Las compensaciones fiscales se congelan exclusivamente al cerrar la liquidación.')
            if effective_date < fund.effective_date:
                raise ValueError('No se pueden aplicar fondos antes de recibirlos.')
            # A request namespace covers all allocations, rather than each row
            # inventing an independent retry token.
            run = db.get(FeeCompensationRun, key)
            if run:
                if run.fingerprint != digest:
                    raise ValueError('Solicitud ya utilizada con otros datos.')
                return list(db.scalars(select(FeeCompensation).where(
                    FeeCompensation.request_key.like(key + ':%')).order_by(FeeCompensation.id)))
            if db.scalar(select(OwnerPayout.id).where(OwnerPayout.settlement_id == settlement_id).limit(1)):
                raise ValueError('La liquidación ya tiene transferencias; no se reutilizan sus fondos.')
            db.add(FeeCompensationRun(request_key=key, fingerprint=digest))
            obligations = [r for r in self.balances(db, fund.owner_id) if r.effective_date <= effective_date]
            plan = compensation_plan(fund.owner_id, self.fund_available(db, fund), obligations)
            rows = []
            for allocation in plan['applications']:
                row = FeeCompensation(obligation_id=int(allocation['obligation_key']), fund_id=fund_id,
                    settlement_id=settlement_id, effective_date=effective_date,
                    amount=money(allocation['amount']), direction='application',
                    request_key=f"{key}:{allocation['obligation_key']}")
                db.add(row)
                rows.append(row)
            db.flush()
        return rows

    def reverse(self, db, *, application_id, settlement_id, amount, effective_date, reason, request_key):
        amount, key = money(amount), request_id(request_key)
        reason = str(reason or '').strip()
        if amount <= ZERO or not reason or len(reason) > 255 or type(effective_date) is not date:
            raise ValueError('Informe importe positivo, fecha y motivo de corrección.')
        with financial_transaction(db):
            previous = db.scalar(select(FeeCompensation).where(FeeCompensation.request_key == key))
            if previous:
                if (previous.direction != 'reversal' or previous.corrects_id != application_id
                        or previous.settlement_id != settlement_id or previous.amount != amount
                        or previous.effective_date != effective_date or previous.reason != reason):
                    raise ValueError('Solicitud ya utilizada con otros datos.')
                return previous
            original = db.get(FeeCompensation, application_id)
            settlement = db.get(OwnerSettlement, settlement_id)
            if settlement and settlement.selection.get('billing'):
                raise ValueError('La corrección fiscal debe proceder de una devolución trazada al cerrar una nueva liquidación.')
            obligation = db.get(FeeObligation, original.obligation_id) if original else None
            if (original is None or original.direction != 'application' or settlement is None
                    or settlement.status != 'closed' or settlement.owner_id != obligation.owner_id
                    or effective_date < original.effective_date):
                raise ValueError('Origen o liquidación de corrección no válido.')
            reversed_amount = sum(db.scalars(select(FeeCompensation.amount).where(
                FeeCompensation.corrects_id == application_id)), ZERO)
            if reversed_amount + amount > original.amount:
                raise ValueError('La corrección supera la aplicación original.')
            row = FeeCompensation(obligation_id=original.obligation_id, fund_id=original.fund_id,
                settlement_id=settlement_id, effective_date=effective_date, amount=amount,
                direction='reversal', corrects_id=original.id, request_key=key, reason=reason)
            db.add(row)
        return row
