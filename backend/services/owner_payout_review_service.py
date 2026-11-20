"""Preview for the existing payout service, including evidence of distinct outflows."""
from datetime import date
from sqlalchemy import select
from backend.core.business_time import business_today
from backend.models.owner_settlement import OwnerPayout,OwnerSettlement
from backend.models.owner_bank_account import OwnerBankAccount
from backend.models.owner_payout_correction import OwnerPayoutCorrectionOperation
from backend.models.owner_transfer_incident import OwnerTransferOutflow,OwnerTransferIdentity
from backend.models.owner_transfer_recovery import OwnerPayoutReview
from backend.services.owner_payout_balance_service import OwnerPayoutBalanceService
from backend.services.owner_transfer_incident_service import account,bank_id,safe
from backend.services.owner_payout_correction_service import raw
from backend.services.expense_service import fingerprint
from backend.services.settlement_money import money


class OwnerPayoutReviewService:
    def preview(self,db,settlement_id,**inputs):
        s=db.get(OwnerSettlement,settlement_id)
        if s is None:raise LookupError('Liquidación no encontrada.')
        if s.status!='closed':raise ValueError('La liquidación debe estar cerrada.')
        b=OwnerPayoutBalanceService().summary(db,s)
        if b['payout_blockers']:raise ValueError(' '.join(b['payout_blockers']))
        if OwnerPayoutBalanceService().pending_returns(db,s.owner_id):raise ValueError('Hay devoluciones pendientes de liquidar.')
        amount=money(inputs.get('amount'))
        if amount<=0 or amount>min(b['remaining'],b['available']):raise ValueError('Importe superior al pendiente o a los fondos disponibles, o no positivo.')
        try:day=date.fromisoformat(str(inputs.get('effective_date')));aid=int(inputs.get('bank_account_id'))
        except (TypeError,ValueError):raise ValueError('Fecha y cuenta destino obligatorias.') from None
        if day>business_today():raise ValueError('Fecha futura no permitida.')
        a=db.get(OwnerBankAccount,aid)
        if a is None or a.owner_id!=s.owner_id or not a.active or not a.receives_settlements:raise ValueError('Cuenta activa del propietario obligatoria.')
        reason=str(inputs.get('reason') or '').strip();reference=str(inputs.get('reference') or '').strip()
        if not reason or len(reason)>2000 or len(reference)>255:raise ValueError('Motivo obligatorio y referencia de hasta 255 caracteres.')
        if inputs.get('paid') is not True:raise ValueError('Confirme que este nuevo pago ya se ha efectuado. No se ordena una transferencia.')
        source,_=account(inputs.get('source_iban'));bid=bank_id(inputs.get('bank_transaction_id'));oldbid=bank_id(inputs.get('previous_bank_id'))
        try:oldid=int(inputs.get('previous_payout_id')) if inputs.get('previous_payout_id') else None
        except (ValueError,TypeError):raise ValueError('Pago anterior no válido.') from None
        if bid and not source:raise ValueError('Identifique la cuenta de origen para contrastar el identificador bancario.')
        identities=list(db.scalars(select(OwnerTransferIdentity)))
        key=fingerprint(['bank',source,bid]) if bid else None
        if key and any(i.bank_key==key or (i.bank_transaction_id==bid and not i.source_account_hash) for i in identities):raise ValueError('Salida bancaria ya registrada.')
        dest,_=account(a.iban);old_identity=None
        for out in db.scalars(select(OwnerTransferOutflow).where(OwnerTransferOutflow.amount==amount,OwnerTransferOutflow.effective_date==day)):
            if out.destination_hash and out.destination_hash!=dest:continue
            if not bid or not out.bank_transaction_id or not source or source!=out.source_account_hash or bid==out.bank_transaction_id:
                raise ValueError('Posible salida extraordinaria duplicada: se requieren identificadores bancarios distintos y origen verificable.')
        all_payouts=list(db.scalars(select(OwnerPayout).order_by(OwnerPayout.id)))
        all_corrections=list(db.scalars(select(OwnerPayoutCorrectionOperation)))
        invalid={o.original_payout_id for o in all_corrections};parents={o.replacement_payout_id:o.original_payout_id for o in all_corrections if o.replacement_payout_id}
        for p in all_payouts:
            if p.id in invalid or p.amount!=amount or p.effective_date!=day or account(p.account_snapshot.get('iban'))[0]!=dest:continue
            root=p.id
            while root in parents:root=parents[root]
            identity=next((i for i in identities if i.payout_root_id==root),None)
            prior_id=identity.bank_transaction_id if identity else oldbid if oldid==p.id else None
            if not bid or not source or not prior_id or bid==prior_id or (identity and identity.source_account_hash!=source):
                raise ValueError('Posible payout duplicado: identifique ambos movimientos bancarios distintos y su origen.')
            if not identity:
                if old_identity:raise ValueError('Varias transferencias anteriores sin identificar; requiere revisión.')
                oldkey=fingerprint(['bank',source,prior_id])
                if any(i.bank_key==oldkey for i in identities):raise ValueError('Identificador anterior ya vinculado a otro movimiento.')
                old_identity=dict(payout_root_id=root,bank_key=oldkey,source_account_hash=source,bank_transaction_id=prior_id)
        values=dict(amount=str(amount),effective_date=str(day),bank_account_id=aid,reference=reference,reason=reason,paid=True,
            source_account_hash=source,bank_transaction_id=bid,previous_payout_id=oldid,previous_bank_id=oldbid)
        impact=dict(paid_before=str(b['paid']),paid_after=str(b['paid']+amount),remaining_before=str(b['remaining']),remaining_after=str(b['remaining']-amount),available_before=str(b['available']),available_after=str(b['available']-amount))
        state=[b['incident_state'],[raw(x) for x in all_payouts],[raw(x) for x in all_corrections],[raw(x) for x in b['all_returns']],
            [raw(x) for x in b['closed']],raw(a),[raw(x) for x in identities],values,impact]
        return dict(settlement=s,balance=b,account=a,values=values,impact=impact,fingerprint=fingerprint(state),bank_key=key,old_identity=old_identity)

    def record(self,db,payout,view,expected,operator_id=None):
        v=view['values']
        if view['bank_key']:db.add(OwnerTransferIdentity(payout_root_id=payout.id,bank_key=view['bank_key'],source_account_hash=v['source_account_hash'],bank_transaction_id=v['bank_transaction_id']))
        if view['old_identity']:db.add(OwnerTransferIdentity(**view['old_identity']))
        values=dict(v,reason=safe(v['reason']),reference=safe(v['reference']))
        db.add(OwnerPayoutReview(payout_id=payout.id,reason=safe(v['reason']),operator_id=str(operator_id)[:160] if operator_id else None,
            fingerprint=fingerprint(values),reviewed_state=expected,values=values,impact=view['impact']));db.flush()

    def confirm(self,db,settlement_id,*,request_key,expected,confirmed=False,operator_id=None,**inputs):
        if confirmed is not True:raise ValueError('Confirme expresamente el impacto revisado.')
        # The ordinary service owns the transaction and repeats this preview under lock.
        from backend.services.owner_settlement_service import OwnerSettlementService
        try:day=date.fromisoformat(str(inputs.get('effective_date')));aid=int(inputs.get('bank_account_id'))
        except (ValueError,TypeError):raise ValueError('Fecha y cuenta obligatorias.') from None
        return OwnerSettlementService().payout(db,settlement_id,amount=inputs.get('amount'),effective_date=day,bank_account_id=aid,
            method='bank_transfer',reference=inputs.get('reference'),request_key=request_key,reviewed=dict(inputs=inputs,expected=expected,operator_id=operator_id))
