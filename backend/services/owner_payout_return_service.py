"""Confirmed real bank returns of correctly addressed owner transfers only."""
from datetime import date
from hashlib import sha256
import unicodedata
from sqlalchemy import select,inspect
from backend.core.business_time import business_today
from backend.core.iban import normalize_iban,is_valid_iban
from backend.models.owner_settlement import OwnerPayout,OwnerSettlement
from backend.models.owner_payout_return import OwnerPayoutReturn
from backend.services.owner_payout_balance_service import OwnerPayoutBalanceService
from backend.services.owner_payout_correction_service import raw,redact
from backend.services.expense_service import fingerprint,request_id
from backend.services.financial_transaction import financial_transaction
from backend.services.settlement_money import money,ZERO


class OwnerPayoutReturnService:
    balances=OwnerPayoutBalanceService()

    def form(self,db,settlement_id,payout_id):
        settlement=db.get(OwnerSettlement,settlement_id);selected=db.get(OwnerPayout,payout_id)
        if settlement is None or selected is None or selected.settlement_id!=settlement_id:raise LookupError('Pago no encontrado en esta liquidación.')
        b=self.balances.summary(db,settlement);root=b['roots'][selected.id];active=b['active_by_root'].get(root)
        p=active or selected;blockers=[]
        if settlement.status!='closed':blockers.append('La liquidación debe estar cerrada; su cierre no se modificará.')
        if active is None:blockers.append('El pago está anulado administrativamente. No admite una devolución bancaria.')
        if p.owner_id!=settlement.owner_id or p.method!='bank_transfer' or not p.account_snapshot.get('iban'):blockers.append('Transferencia o beneficiario no identificados inequívocamente. Requiere otro procedimiento.')
        from backend.models.owner_transfer_incident import OwnerTransferIncident
        if db.scalar(select(OwnerTransferIncident.id).where(OwnerTransferIncident.payout_root_id==root)):blockers.append('Transferencia con incidencia bancaria: su recuperación requiere el circuito específico, todavía no habilitado.')
        if settlement.selection.get('billing'):blockers.append('Liquidación con compensaciones de facturación. Requiere revisión específica.')
        if inspect(db.connection()).has_table('fee_compensations'):
            from backend.models.fee_billing import FeeCompensation
            if db.scalar(select(FeeCompensation.id).where(FeeCompensation.settlement_id==settlement_id).limit(1)):blockers.append('Existen compensaciones vinculadas; no se alteran sus fondos mediante este circuito.')
        returned=b['returned_by_root'].get(root,ZERO);maximum=p.amount-returned if active else ZERO
        if maximum<=ZERO and active:blockers.append('El pago ya está devuelto íntegramente.')
        return dict(settlement=settlement,selected=selected,payout=p,root_id=root,balance=b,returned=returned,maximum=maximum,blockers=blockers,history=[r for r in b['returns'] if r.transfer_root_id==root])

    def normalized(self,amount=None,effective_date=None,bank_reference=None,reason=None,receiving_iban=None,bank_transaction_id=None,received=False):
        if received is not True:raise ValueError('Confirme que el dinero ya está abonado en la cuenta identificada y corresponde a una transferencia destinada correctamente al propietario.')
        amount=money(amount)
        if amount<=ZERO:raise ValueError('El importe devuelto debe ser positivo.')
        try:day=date.fromisoformat(str(effective_date))
        except (ValueError,TypeError):raise ValueError('Indique una fecha efectiva válida.') from None
        if day>business_today():raise ValueError('La fecha de recepción no puede ser futura.')
        reason=(reason or '').strip();reference=(bank_reference or '').strip()
        if not reason or len(reason)>1000:raise ValueError('Indique un motivo de hasta 1000 caracteres.')
        if not reference or len(reference)>255:raise ValueError('Indique la referencia bancaria de hasta 255 caracteres.')
        account=normalize_iban(receiving_iban)
        if not is_valid_iban(account):raise ValueError('Identifique mediante un IBAN válido la cuenta que recibió efectivamente el abono.')
        bank_id=unicodedata.normalize('NFKC',bank_transaction_id or '').strip().upper() or None
        if bank_id and (len(bank_id)>160 or any(ord(c)<32 for c in bank_id)):raise ValueError('Identificador bancario no válido.')
        return dict(amount=str(amount),effective_date=day.isoformat(),bank_reference=reference,reason=reason,receiving_iban=account,bank_transaction_id=bank_id,received=True)

    def digest_values(self,values):
        return {k:v for k,v in values.items() if k!='receiving_iban'}|{'receiving_account_hash':sha256(values['receiving_iban'].encode()).hexdigest()}

    def preview(self,db,settlement_id,payout_id,**inputs):
        v=self.normalized(**inputs);view=self.form(db,settlement_id,payout_id)
        if view['blockers']:raise ValueError(' '.join(view['blockers']))
        p=view['payout'];amount=money(v['amount']);day=date.fromisoformat(v['effective_date'])
        if day<p.effective_date:raise ValueError('La devolución no puede recibirse antes de la transferencia.')
        if amount>view['maximum']:raise ValueError('La devolución supera el importe pagado todavía no devuelto.')
        account_hash=self.digest_values(v)['receiving_account_hash']
        dedupe=fingerprint(['bank',account_hash,v['bank_transaction_id']]) if v['bank_transaction_id'] else fingerprint(['possible',view['root_id'],v['effective_date'],v['amount']])
        if db.scalar(select(OwnerPayoutReturn.id).where(OwnerPayoutReturn.dedupe_key==dedupe).limit(1)):raise ValueError('Este abono ya está registrado o coincide con una devolución existente. Revise el historial.')
        matches=list(db.scalars(select(OwnerPayoutReturn).where(OwnerPayoutReturn.transfer_root_id==view['root_id'],OwnerPayoutReturn.effective_date==day,OwnerPayoutReturn.amount==amount)))
        if any(not v['bank_transaction_id'] or not r.bank_transaction_id or (r.receiving_account_hash==account_hash and r.bank_transaction_id==v['bank_transaction_id']) for r in matches):raise ValueError('Posible duplicado: misma transferencia, fecha e importe. Se requieren identificadores bancarios distintos y verificables para distinguir los abonos; no cambie la referencia para eludir la revisión.')
        b=view['balance'];impact=dict(gross=str(b['gross_paid']),returned_before=str(b['returned']),returned_after=str(b['returned']+amount),paid_before=str(b['paid']),paid_after=str(b['paid']-amount),remaining_before=str(b['remaining']),remaining_after=str(b['remaining']+amount),available_before=str(b['available']),available_after=str(ZERO if b['payout_blockers'] else max(ZERO,b['owner_funds']-b['cash_used']+amount)))
        state=dict(incidents=b['incident_state'],payouts=[raw(r) for r in b['all_payouts']],operations=[raw(r) for r in b['operations']],returns=[raw(r) for r in b['all_returns']],closed=[raw(r) for r in b['closed']],values=self.digest_values(v),selected=payout_id)
        return dict(**view,values=v,impact=impact,dedupe_key=dedupe,account_hash=account_hash,fingerprint=fingerprint(state))

    def confirm(self,db,settlement_id,payout_id,*,request_key,expected,confirmed=False,operator_id=None,**inputs):
        if confirmed is not True:raise ValueError('Confirme expresamente el impacto revisado.')
        v=self.normalized(**inputs);key=request_id(request_key);digest=fingerprint([settlement_id,payout_id,self.digest_values(v)])
        with financial_transaction(db):
            prior=db.scalar(select(OwnerPayoutReturn).where(OwnerPayoutReturn.request_key==key))
            if prior:
                if prior.fingerprint!=digest:raise ValueError('Solicitud ya utilizada con otros datos.')
                return prior
            view=self.preview(db,settlement_id,payout_id,**v)
            if view['fingerprint']!=expected:raise ValueError('Los datos han cambiado. Revise de nuevo la devolución.')
            row=OwnerPayoutReturn(payout_id=view['payout'].id,transfer_root_id=view['root_id'],amount=money(v['amount']),effective_date=date.fromisoformat(v['effective_date']),bank_reference=redact(v['bank_reference']),bank_transaction_id=v['bank_transaction_id'],receiving_account_hash=view['account_hash'],receiving_account_suffix=v['receiving_iban'][-4:],reason=redact(v['reason']),received=True,operator_id=str(operator_id)[:160] if operator_id is not None else None,request_key=key,dedupe_key=view['dedupe_key'],fingerprint=digest,reviewed_state=expected,impact=view['impact'])
            db.add(row);db.flush();self.balances.summary(db,view['settlement'])
        return row
