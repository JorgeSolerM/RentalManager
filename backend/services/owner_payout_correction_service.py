"""Administrative representations only; no bank instructions or cash movements."""
from datetime import date
from copy import deepcopy
from uuid import uuid4
import re
from sqlalchemy import select,inspect
from backend.core.business_time import business_today
from backend.models.owner_settlement import OwnerPayout,OwnerSettlement
from backend.models.owner_payout_correction import OwnerPayoutCorrectionOperation as Operation
from backend.services.owner_payout_balance_service import OwnerPayoutBalanceService
from backend.services.expense_service import fingerprint,request_id
from backend.services.financial_transaction import financial_transaction
from backend.services.settlement_money import money


def raw(row):
    return {c.name:getattr(row,c.name) for c in row.__table__.columns}


def redact(value):
    return re.sub(r'\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b',lambda m:'[cuenta …'+m.group().replace(' ','')[-4:]+']',str(value or ''))


def snapshot(p):
    return dict(id=p.id,settlement_id=p.settlement_id,owner_id=p.owner_id,amount=str(p.amount),effective_date=str(p.effective_date),method=p.method,reference=redact(p.reference),bank_account_id=p.bank_account_id,account_suffix=(p.account_snapshot.get('iban') or '')[-4:])


class OwnerPayoutCorrectionService:
    balances=OwnerPayoutBalanceService()

    def form(self,db,settlement_id,payout_id):
        settlement=db.get(OwnerSettlement,settlement_id);payout=db.get(OwnerPayout,payout_id)
        if not settlement or not payout or payout.settlement_id!=settlement_id:raise LookupError('Pago no encontrado en esta liquidación.')
        balance=self.balances.summary(db,settlement)
        blockers=[]
        if settlement.status!='closed':blockers.append('Solo se revisan pagos de liquidaciones cerradas; no se modifica el cierre.')
        if payout.owner_id!=settlement.owner_id or not payout.account_snapshot.get('iban'):blockers.append('Beneficiario o cuenta histórica ambiguos. Requiere revisión específica.')
        if balance['states'][payout.id]!='posted':blockers.append('El registro ya está anulado o sustituido. Consulte el historial y revise el pago vigente.')
        if settlement.selection.get('billing'):blockers.append('Liquidación con compensaciones de facturación: requiere revisión específica; este circuito no altera sus fondos.')
        # Compatibility guard only: no dependency on applying the fiscal migration.
        if inspect(db.connection()).has_table('fee_compensations'):
            from backend.models.fee_billing import FeeCompensation
            if db.scalar(select(FeeCompensation.id).where(FeeCompensation.settlement_id==settlement_id).limit(1)):
                blockers.append('Existen compensaciones vinculadas. Requiere revisión específica; no se reutilizan sus fondos.')
        if self.balances.pending_returns(db,settlement.owner_id):blockers.append('Hay devoluciones pendientes de liquidar. Resuelva esa regularización antes de corregir pagos.')
        return dict(settlement=settlement,payout=payout,balance=balance,blockers=blockers,history=[o for o in balance['operations'] if any(p.id==o.original_payout_id for p in balance['payouts'])])

    def normalized(self,kind,reason,amount=None,effective_date=None,reference=None,no_transfer=False,same_transfer=False):
        reason=(reason or '').strip()
        if not reason or len(reason)>1000:raise ValueError('Indique un motivo obligatorio de hasta 1000 caracteres.')
        if kind not in ('void','replace'):raise ValueError('Operación no válida.')
        values=dict(kind=kind,reason=reason)
        if kind=='void':
            if no_transfer is not True:raise ValueError('Confirme que no hubo transferencia real. Una devolución bancaria requiere otro procedimiento.')
            values['no_transfer']=True
        else:
            if same_transfer is not True:raise ValueError('Confirme que corrige el registro de la misma transferencia al mismo propietario, sin ordenar otra.')
            amount=money(amount)
            try:effective_date=date.fromisoformat(str(effective_date))
            except (ValueError,TypeError):raise ValueError('Indique una fecha efectiva válida.') from None
            if amount<=0 or effective_date>business_today():raise ValueError('Importe positivo y fecha no futura obligatorios.')
            reference=(reference or '').strip()
            if len(reference)>255:raise ValueError('Referencia demasiado larga.')
            values.update(amount=str(amount),effective_date=effective_date.isoformat(),reference=reference,same_transfer=True)
        return values

    def preview(self,db,settlement_id,payout_id,**values):
        values=self.normalized(**values);view=self.form(db,settlement_id,payout_id)
        if view['blockers']:raise ValueError(' '.join(view['blockers']))
        p,b=view['payout'],view['balance'];limits=self.balances.summary(db,view['settlement'],exclude_id=p.id)
        new=money(values['amount']) if values['kind']=='replace' else money('0')
        if new>limits['remaining'] or new>limits['available']:raise ValueError('El importe corregido supera el pendiente de la liquidación o los fondos disponibles del propietario.')
        if values['kind']=='replace' and new==p.amount and values['effective_date']==str(p.effective_date) and values['reference']==(p.reference or ''):raise ValueError('No hay cambios que registrar.')
        before=snapshot(p);after=dict(before,amount=str(new),state='void' if values['kind']=='void' else 'replacement')
        if values['kind']=='replace':after.update(effective_date=values['effective_date'],reference=redact(values['reference']))
        paid=limits['paid']+new;available=max(money('0'),limits['owner_funds']-limits['owner_paid']-new)
        impact=dict(paid_before=str(b['paid']),paid_after=str(paid),remaining_before=str(b['remaining']),remaining_after=str(b['due']-paid),available_before=str(b['available']),available_after=str(available),amount_before=str(p.amount),amount_after=str(new))
        state=dict(payouts=[raw(p) for p in b['all_payouts']],operations=[raw(o) for o in b['operations']],closed=[raw(s) for s in b['closed']],values=values,payout_id=payout_id,settlement_id=settlement_id)
        return dict(**view,values=values,before=before,after=after,impact=impact,fingerprint=fingerprint(state))

    def confirm(self,db,settlement_id,payout_id,*,request_key,expected,confirmed=False,operator_id=None,**values):
        if confirmed is not True:raise ValueError('Confirme expresamente el impacto revisado.')
        values=self.normalized(**values);key=request_id(request_key);digest=fingerprint([settlement_id,payout_id,values])
        with financial_transaction(db):
            prior=db.get(Operation,key)
            if prior:
                if prior.fingerprint!=digest:raise ValueError('La solicitud ya se utilizó con otros datos.')
                return prior
            view=self.preview(db,settlement_id,payout_id,**values)
            if expected!=view['fingerprint']:raise ValueError('Los datos han cambiado. Revise nuevamente el impacto.')
            p=view['payout'];replacement=None
            if values['kind']=='replace':
                replacement=OwnerPayout(settlement_id=p.settlement_id,owner_id=p.owner_id,amount=money(values['amount']),effective_date=date.fromisoformat(values['effective_date']),bank_account_id=p.bank_account_id,account_snapshot=deepcopy(p.account_snapshot),method=p.method,reference=values['reference'] or None,notes=p.notes,request_key=str(uuid4()),fingerprint=fingerprint(['administrative-replacement',key]))
                db.add(replacement);db.flush()
            after=snapshot(replacement) if replacement else dict(view['before'],state='void')
            op=Operation(request_key=key,original_payout_id=p.id,replacement_payout_id=replacement.id if replacement else None,kind=values['kind'],reason=redact(values['reason']),no_transfer=values['kind']=='void',operator_id=str(operator_id)[:160] if operator_id is not None else None,before_state=view['before'],after_state=after,impact=view['impact'],fingerprint=digest,reviewed_state=expected)
            db.add(op);db.flush()
            self.balances.summary(db,view['settlement'])
        return op
