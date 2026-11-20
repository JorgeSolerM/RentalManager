"""Confirmed receipts, immutable attribution and documentary links. No bank execution."""
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from backend.core.business_time import business_today
from backend.models.owner_settlement import OwnerPayout, OwnerSettlement
from backend.models.owner_payout_return import OwnerPayoutReturn
from backend.models.owner_payout_correction import OwnerPayoutCorrectionOperation
from backend.models.owner_transfer_recovery import OwnerTransferRecovery as Recovery, OwnerRecoveryAttribution as Attribution, OwnerRecoveryReturnLink as ReturnLink
from backend.services.owner_transfer_incident_service import OwnerTransferIncidentService, account, bank_id, safe
from backend.services.owner_transfer_state import recovery_state, incident_effects
from backend.services.owner_payout_balance_service import OwnerPayoutBalanceService
from backend.services.owner_payout_correction_service import raw
from backend.services.owner_bank_credit_service import validate_credit, register_identity
from backend.services.expense_service import fingerprint,request_id
from backend.services.financial_transaction import financial_transaction
from backend.services.settlement_money import money,ZERO


class OwnerTransferRecoveryService:
    incidents=OwnerTransferIncidentService()
    balances=OwnerPayoutBalanceService()

    def form(self,db,incident_id):
        view=self.incidents.detail(db,incident_id);incident=view['incident']
        all_rows,parts,audit=recovery_state(db);rows=[r for r in all_rows if r.incident_id==incident_id]
        received=sum((r.amount for r in rows),ZERO)
        if received>incident.affected_amount:raise ValueError('Historial de recuperaciones incoherente.')
        previous=list(db.scalars(select(OwnerPayoutReturn).where(OwnerPayoutReturn.transfer_root_id==incident.payout_root_id))) if incident.payout_root_id else []
        if incident.payout_root_id:
            original=view['balance']['active_by_root'].get(incident.payout_root_id)
            if original is None:raise ValueError('Pago original anulado; requiere revisión específica.')
            original_date=original.effective_date
        else:original_date=view['outflow'].effective_date
        links=list(db.scalars(select(ReturnLink).where(ReturnLink.incident_id==incident_id)))
        return dict(**view,recoveries=rows,recovery_allocations=parts,recovery_audit=audit,previous_returns=previous,
            previous_returned=sum((r.amount for r in previous),ZERO),recovered=received,maximum=incident.affected_amount-received,
            original_date=original_date,links=links,unattributed=sum((r.amount for r in rows if not parts[r.id]),ZERO))

    def state(self,db,view):
        return dict(incident=view['balance']['incident_state'],payouts=[raw(r) for r in db.scalars(select(OwnerPayout))],
            corrections=[raw(r) for r in db.scalars(select(OwnerPayoutCorrectionOperation))],
            returns=[raw(r) for r in db.scalars(select(OwnerPayoutReturn))],
            closed=[raw(r) for r in db.scalars(select(OwnerSettlement).where(OwnerSettlement.status=='closed'))])

    def distribution(self,db,view,amount,requested,exclude=None):
        original=view['state'].get('allocations',{})
        requested={k:v for k,v in (requested or {}).items() if v not in ('',None)}
        if not original:
            if requested:raise ValueError('Atribuya primero los fondos de la salida; el ingreso permanece pendiente de atribución.')
            return {}
        if not requested and len(original)==1:requested={next(iter(original)):str(amount)}
        if not requested:raise ValueError('Indique la distribución entre los propietarios afectados.')
        parts=self.incidents.allocations(db,requested,amount)
        used={k:ZERO for k in original}
        for row in view['recoveries']:
            if row.id==exclude:continue
            for owner,value in view['recovery_allocations'][row.id].items():used[owner]=used.get(owner,ZERO)+Decimal(value)
        for owner,value in parts.items():
            if owner not in original or Decimal(value)>Decimal(original[owner])-used[owner]:
                raise ValueError('La recuperación no puede atribuirse a otro propietario ni superar sus fondos afectados pendientes.')
        return parts

    def impacts(self,db,view,amount,parts,attributing=None):
        effects={}
        for owner,value in parts.items():
            s=db.scalar(select(OwnerSettlement).where(OwnerSettlement.owner_id==int(owner),OwnerSettlement.status=='closed').order_by(OwnerSettlement.id))
            if s:b=self.balances.summary(db,s)
            else:
                e=incident_effects(db,int(owner),0);b=dict(owner_funds=ZERO,cash_used=e['extra']-e['restored'],available=ZERO,payout_blockers=e['blockers'])
            blocks=[x for x in b['payout_blockers'] if not attributing or not x.startswith(f'Recuperación #{attributing}:')]
            net=b['owner_funds']-b['cash_used']+Decimal(value)
            effects[owner]=dict(restored=value,available_before=str(b['available']),available_after=str(ZERO if blocks else max(ZERO,net)),deficit_after=str(max(ZERO,-net)),blockers=blocks)
        b=view['balance'];credited=amount if view['incident'].receipt_accredited and not attributing else ZERO
        return dict(recovered_before=str(view['recovered']),recovered_after=str(view['recovered']+(ZERO if attributing else amount)),
            pending_after=str(view['maximum']-(ZERO if attributing else amount)),paid_before=str(b['paid']),paid_after=str(b['paid']-credited),
            remaining_before=str(b['remaining']),remaining_after=str(b['remaining']+credited),funds=effects,unattributed=not bool(parts))

    def normalized(self,**v):
        if v.get('received') is not True:raise ValueError('Confirme que el dinero ha sido efectivamente recibido.')
        amount=money(v.get('amount'))
        if amount<=ZERO:raise ValueError('Importe positivo obligatorio.')
        try:day=date.fromisoformat(str(v.get('effective_date')))
        except (ValueError,TypeError):raise ValueError('Fecha efectiva válida obligatoria.') from None
        if day>business_today():raise ValueError('La recepción no puede ser futura.')
        h,suffix=account(v.get('receiving_iban'))
        if not h:raise ValueError('Identifique la cuenta que recibió el ingreso.')
        text={k:str(v.get(k) or '').strip() for k in ('reason','evidence','bank_reference')}
        if any(not x for x in text.values()) or any(len(x)>2000 for x in text.values()) or len(text['bank_reference'])>255:raise ValueError('Motivo, evidencia y referencia obligatorios; revise su longitud.')
        return dict(amount=str(amount),effective_date=str(day),receiving_account_hash=h,receiving_account_suffix=suffix,
            bank_transaction_id=bank_id(v.get('bank_transaction_id')),**text,allocations=v.get('allocations') or {},received=True)

    def preview(self,db,incident_id,**inputs):
        v=self.normalized(**inputs);view=self.form(db,incident_id);amount=money(v['amount']);day=date.fromisoformat(v['effective_date'])
        if amount>view['maximum']:raise ValueError('La recuperación supera el importe pendiente de recuperar.')
        if day<view['original_date']:raise ValueError('No puede recuperarse antes de la salida original.')
        validate_credit(db,account_hash=v['receiving_account_hash'],bank_id=v['bank_transaction_id'],day=day,amount=amount,source=('payout',view['incident'].payout_root_id) if view['incident'].payout_root_id else ('incident',incident_id))
        parts=self.distribution(db,view,amount,v['allocations']);impact=self.impacts(db,view,amount,parts)
        return dict(**view,values=v,parts=parts,impact=impact,fingerprint=fingerprint([self.state(db,view),v,parts,impact]))

    def confirm(self,db,incident_id,*,request_key,expected,confirmed=False,operator_id=None,**inputs):
        if confirmed is not True:raise ValueError('Confirme el impacto revisado.')
        v=self.normalized(**inputs);key=request_id(request_key);digest=fingerprint([incident_id,v])
        with financial_transaction(db):
            old=db.scalar(select(Recovery).where(Recovery.request_key==key))
            if old:
                if old.fingerprint!=digest:raise ValueError('Clave utilizada con otros datos.')
                return old
            view=self.preview(db,incident_id,**inputs)
            if view['fingerprint']!=expected:raise ValueError('Los saldos han cambiado; revise nuevamente.')
            row=Recovery(incident_id=incident_id,amount=money(v['amount']),effective_date=date.fromisoformat(v['effective_date']),
                receiving_account_hash=v['receiving_account_hash'],receiving_account_suffix=v['receiving_account_suffix'],
                bank_transaction_id=v['bank_transaction_id'],bank_reference=safe(v['bank_reference']),reason=safe(v['reason']),evidence=safe(v['evidence']),
                received=True,operator_id=str(operator_id)[:160] if operator_id else None,request_key=key,fingerprint=digest,reviewed_state=expected,allocations=view['parts'],impact=view['impact'])
            db.add(row);db.flush();register_identity(db,row,recovery=True);self.balances.summary(db,view['settlement'])
        return row

    def attribution_preview(self,db,recovery_id,*,allocations=None,reason=None):
        row=db.get(Recovery,recovery_id)
        if row is None:raise LookupError('Recuperación no encontrada.')
        view=self.form(db,row.incident_id)
        if view['recovery_allocations'][row.id]:raise ValueError('La recuperación ya está atribuida; no se redistribuye.')
        if not str(reason or '').strip():raise ValueError('Motivo y evidencia de atribución obligatorios.')
        parts=self.distribution(db,view,row.amount,allocations,exclude=row.id)
        if not parts:raise ValueError('Identifique primero los fondos de la salida original.')
        impact=self.impacts(db,view,row.amount,parts,attributing=row.id)
        return dict(**view,recovery=row,parts=parts,reason=reason,impact=impact,fingerprint=fingerprint([self.state(db,view),row.id,parts,reason,impact]))

    def attribute(self,db,recovery_id,*,allocations,reason,request_key,expected,confirmed=False,operator_id=None):
        if confirmed is not True:raise ValueError('Confirme la atribución revisada.')
        key=request_id(request_key);digest=fingerprint([recovery_id,allocations,reason])
        with financial_transaction(db):
            old=db.scalar(select(Attribution).where(Attribution.request_key==key))
            if old:
                if old.fingerprint!=digest:raise ValueError('Clave utilizada con otros datos.')
                return old
            v=self.attribution_preview(db,recovery_id,allocations=allocations,reason=reason)
            if expected!=v['fingerprint']:raise ValueError('Los fondos han cambiado; revise nuevamente.')
            row=Attribution(recovery_id=recovery_id,allocations=v['parts'],reason=safe(reason),operator_id=str(operator_id)[:160] if operator_id else None,
                request_key=key,fingerprint=digest,reviewed_state=expected)
            db.add(row);db.flush()
        return row

    def link_preview(self,db,incident_id,*,return_id,reason):
        view=self.form(db,incident_id)
        try:rid=int(return_id)
        except (TypeError,ValueError):raise ValueError('Devolución válida obligatoria.') from None
        row=next((r for r in view['previous_returns'] if r.id==rid),None)
        if row is None:raise ValueError('La devolución no pertenece a esta transferencia.')
        if not str(reason or '').strip():raise ValueError('Motivo documental obligatorio.')
        if db.scalar(select(ReturnLink.id).where(ReturnLink.return_id==rid)):raise ValueError('La devolución ya está vinculada.')
        return dict(**view,linked_return=row,reason=reason,fingerprint=fingerprint([self.state(db,view),rid,reason]))

    def link_return(self,db,incident_id,*,return_id,reason,request_key,expected,confirmed=False,operator_id=None):
        if confirmed is not True:raise ValueError('Confirme que el vínculo no tiene efecto económico.')
        key=request_id(request_key);digest=fingerprint([incident_id,str(return_id),reason])
        with financial_transaction(db):
            old=db.scalar(select(ReturnLink).where(ReturnLink.request_key==key))
            if old:
                if old.fingerprint!=digest:raise ValueError('Clave utilizada con otros datos.')
                return old
            v=self.link_preview(db,incident_id,return_id=return_id,reason=reason)
            if v['fingerprint']!=expected:raise ValueError('Historial modificado; revise de nuevo.')
            row=ReturnLink(incident_id=incident_id,return_id=v['linked_return'].id,reason=safe(reason),operator_id=str(operator_id)[:160] if operator_id else None,
                request_key=key,fingerprint=digest,reviewed_state=expected)
            db.add(row);db.flush()
        return row
