"""Audited transfer incidents and real extraordinary outflows; no recovery workflow."""
from datetime import date
from decimal import Decimal
from hashlib import sha256
import re, unicodedata
from sqlalchemy import select, inspect
from backend.core.business_time import business_today
from backend.core.iban import normalize_iban,is_valid_iban
from backend.models.owner import Owner
from backend.models.owner_settlement import OwnerPayout,OwnerSettlement
from backend.models.owner_payout_correction import OwnerPayoutCorrectionOperation
from backend.models.owner_transfer_incident import OwnerTransferIncident as Incident,OwnerTransferOutflow as Outflow,OwnerTransferIncidentOperation as Operation,OwnerTransferIdentity as Identity
from backend.services.owner_payout_balance_service import OwnerPayoutBalanceService
from backend.services.owner_transfer_state import incident_state
from backend.services.owner_payout_correction_service import raw
from backend.services.expense_service import fingerprint,request_id
from backend.services.financial_transaction import financial_transaction
from backend.services.settlement_money import money,ZERO

def safe(value):
    return re.sub(r'\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b',lambda m:'[cuenta '+m.group().replace(' ','')[-4:]+']',str(value or ''),flags=re.I)

def account(value):
    v=normalize_iban(value)
    if v and not is_valid_iban(v):raise ValueError('Cuenta bancaria no válida.')
    return (sha256(v.encode()).hexdigest(),v[-4:]) if v else (None,None)

def bank_id(value):
    v=unicodedata.normalize('NFKC',str(value or '')).strip().upper()
    if len(v)>160 or any(ord(c)<32 for c in v):raise ValueError('Identificador bancario no válido.')
    return v or None

def prevent_duplicate_payout(db,amount,day,iban,reference):
    destination,_=account(iban)
    candidates=list(db.scalars(select(Outflow).where(Outflow.amount==amount,Outflow.effective_date==day)))
    if any(not row.destination_hash or row.destination_hash==destination for row in candidates):
        raise ValueError('Posible salida ya registrada como extraordinaria. Revise la incidencia; no registre otro payout para el mismo movimiento.')

class OwnerTransferIncidentService:
    balances=OwnerPayoutBalanceService()

    def context(self,db,settlement_id):
        settlement=db.get(OwnerSettlement,settlement_id)
        if not settlement:raise LookupError('Liquidación no encontrada.')
        if settlement.status!='closed':raise ValueError('La liquidación prevista debe estar cerrada; no se modifica su cierre.')
        return settlement,self.balances.summary(db,settlement)

    def detail(self,db,incident_id):
        incident=db.get(Incident,incident_id)
        if not incident:raise LookupError('Incidencia no encontrada.')
        all_rows,outflows,states,operations=incident_state(db)
        settlement,balance=self.context(db,incident.settlement_id)
        return dict(incident=incident,outflow=outflows.get(incident.id),state=states.get(incident.id,{}),history=[x for x in operations if x.incident_id==incident.id],settlement=settlement,balance=balance)

    def allocations(self,db,values,amount):
        result={}
        if not isinstance(values,dict):raise ValueError('Distribución de fondos no válida.')
        for key,value in values.items():
            if value in ('',None):continue
            try:owner_id=int(key)
            except (TypeError,ValueError):raise ValueError('Propietario de fondos no válido.') from None
            part=money(value)
            if part<=ZERO or not db.get(Owner,owner_id):raise ValueError('Revise propietario e importe de los fondos.')
            if str(owner_id) in result:raise ValueError('Propietario repetido.')
            result[str(owner_id)]=str(part)
        if result and sum((Decimal(x) for x in result.values()),ZERO)!=amount:raise ValueError('La atribución debe sumar exactamente la salida; deje toda la distribución vacía si se desconoce.')
        return dict(sorted(result.items()))

    def normalized(self,db,settlement,**inputs):
        if inputs.get('executed') is not True:raise ValueError('Confirme que la transferencia realmente se ejecutó.')
        kind=inputs.get('kind');source=inputs.get('source_kind')
        if kind not in ('wrong_account','wrong_recipient','unknown_recipient','duplicate') or source not in ('payout','extraordinary'):raise ValueError('Tipo de incidencia o salida no válido.')
        amount=money(inputs.get('amount'))
        if amount<=ZERO:raise ValueError('Importe positivo obligatorio.')
        reason=str(inputs.get('reason') or '').strip();evidence=str(inputs.get('evidence') or '').strip()
        if not reason or not evidence or max(len(reason),len(evidence))>2000:raise ValueError('Motivo y evidencia obligatorios, hasta 2000 caracteres.')
        def optional_id(key):
            value=inputs.get(key)
            try:return int(value) if value not in ('',None) else None
            except (ValueError,TypeError):raise ValueError('Identificador no válido.') from None
        recipient=optional_id('recipient_owner_id');description=str(inputs.get('recipient_description') or '').strip()
        if recipient and not db.get(Owner,recipient):raise ValueError('Destinatario no encontrado.')
        if len(description)>180:raise ValueError('Descripción del destinatario demasiado larga.')
        if kind=='unknown_recipient' and (recipient or description):raise ValueError('No asigne un destinatario a una transferencia desconocida.')
        if kind=='wrong_account' and recipient!=settlement.owner_id:raise ValueError('Indique el mismo propietario y documente su cuenta incorrecta.')
        if kind=='wrong_recipient' and (recipient==settlement.owner_id or not (recipient or description)):raise ValueError('Identifique el destinatario accidental, distinto del propietario previsto.')
        credited=inputs.get('receipt_accredited') is True
        if credited and (kind!='wrong_account' or source!='payout' or recipient!=settlement.owner_id):raise ValueError('Solo puede acreditar recepción del mismo propietario sobre su payout existente.')
        source_hash,source_suffix=account(inputs.get('source_iban'));destination_hash,destination_suffix=account(inputs.get('destination_iban'))
        if source=='payout' and any(x not in ('',None) for x in (inputs.get('allocations') or {}).values()):raise ValueError('El payout conserva su atribución original; deje vacía la distribución extraordinaria.')
        allocations=self.allocations(db,inputs.get('allocations') or {},amount) if source=='extraordinary' else {str(settlement.owner_id):str(amount)}
        scope=[]
        for value in inputs.get('scope') or []:
            try:oid=int(value)
            except (TypeError,ValueError):raise ValueError('Ámbito de fondos no válido.') from None
            if not db.get(Owner,oid):raise ValueError('Ámbito de fondos no válido.')
            scope.append(oid)
        day=None
        if source=='extraordinary':
            try:day=date.fromisoformat(str(inputs.get('effective_date')))
            except (ValueError,TypeError):raise ValueError('Fecha efectiva obligatoria.') from None
            if day>business_today():raise ValueError('La salida no puede ser futura.')
        reference=str(inputs.get('reference') or '').strip()
        if source=='extraordinary' and (not reference or len(reference)>255):raise ValueError('Referencia bancaria obligatoria, hasta 255 caracteres.')
        return dict(kind=kind,source_kind=source,amount=str(amount),reason=reason,evidence=evidence,recipient_owner_id=recipient,recipient_description=description,receipt_accredited=credited,payout_id=optional_id('payout_id'),duplicate_of_id=optional_id('duplicate_of_id'),effective_date=str(day) if day else None,reference=reference,bank_transaction_id=bank_id(inputs.get('bank_transaction_id')),original_bank_id=bank_id(inputs.get('original_bank_id')),source_account_hash=source_hash,source_account_suffix=source_suffix,destination_hash=destination_hash,destination_suffix=destination_suffix,allocations=allocations,scope=sorted(set(scope)),executed=True)

    def bank_key(self,v):
        return fingerprint(['bank',v['source_account_hash'],v['bank_transaction_id']]) if v['bank_transaction_id'] else fingerprint(['possible',v['effective_date'],v['amount'],v['destination_hash']])

    def evaluate(self,db,settlement,b,v):
        amount=Decimal(v['amount']);root=None;duplicate_root=None;identity_existing=None
        if settlement.selection.get('billing'):raise ValueError('Liquidación con compensaciones: requiere un circuito específico.')
        if inspect(db.connection()).has_table('fee_compensations'):
            from backend.models.fee_billing import FeeCompensation
            if db.scalar(select(FeeCompensation.id).where(FeeCompensation.settlement_id==settlement.id).limit(1)):raise ValueError('Existen compensaciones vinculadas; no se alteran mediante este circuito.')
        def active(pid):
            if pid not in b['roots']:raise ValueError('Pago ajeno al propietario o inexistente.')
            root=b['roots'][pid];p=b['active_by_root'].get(root)
            if not p or p.settlement_id!=settlement.id or p.method!='bank_transfer':raise ValueError('El payout debe estar vigente y corresponder a esta liquidación.')
            return root,p
        if v['source_kind']=='payout':
            root,p=active(v['payout_id'])
            if db.scalar(select(Incident.id).where(Incident.payout_root_id==root)):raise ValueError('La transferencia ya tiene una incidencia. Consulte su historial.')
            net=p.amount-b['returned_by_root'].get(root,ZERO)
            if amount>net:raise ValueError('El importe afectado supera lo enviado todavía no devuelto.')
            if v['bank_transaction_id']:
                identity_existing=db.scalar(select(Identity).where(Identity.payout_root_id==root))
                collision=db.scalar(select(Identity).where(Identity.bank_key==self.bank_key(v)))
                if (identity_existing and identity_existing.bank_key!=self.bank_key(v)) or (collision and collision.payout_root_id!=root):raise ValueError('Identificador bancario incompatible con la transferencia.')
            if v['allocations']!={str(settlement.owner_id):str(amount)}:raise ValueError('Se conserva la atribución original del payout.')
        if v['kind']=='duplicate':
            duplicate_root,original=active(v['duplicate_of_id'])
            if root==duplicate_root:raise ValueError('Una transferencia no puede duplicarse a sí misma.')
        if v['source_kind']=='extraordinary':
            key=self.bank_key(v)
            if db.scalar(select(Identity.id).where(Identity.bank_key==key)):raise ValueError('La salida bancaria ya está identificada. No se registra dos veces.')
            if v['bank_transaction_id']:
                same=list(db.scalars(select(Identity).where(Identity.bank_transaction_id==v['bank_transaction_id'])))
                if any(not x.source_account_hash or not v['source_account_hash'] or x.source_account_hash==v['source_account_hash'] for x in same):raise ValueError('Identificador bancario ya utilizado o cuenta de origen ambigua.')
            existing=list(db.scalars(select(Outflow).where(Outflow.amount==amount,Outflow.effective_date==date.fromisoformat(v['effective_date']))))
            for row in existing:
                if not row.destination_hash or not v['destination_hash'] or row.destination_hash==v['destination_hash']:
                    if not row.bank_transaction_id or not v['bank_transaction_id']:raise ValueError('Posible salida duplicada: faltan identificadores bancarios verificables distintos.')
            invalid=set(db.scalars(select(OwnerPayoutCorrectionOperation.original_payout_id)))
            matches=[p for p in db.scalars(select(OwnerPayout).where(OwnerPayout.amount==amount,OwnerPayout.effective_date==date.fromisoformat(v['effective_date']))) if p.id not in invalid and (not v['destination_hash'] or account(p.account_snapshot.get('iban'))[0]==v['destination_hash'])]
            if v['kind']=='duplicate' or matches:
                if not duplicate_root or not v['bank_transaction_id'] or not v['original_bank_id'] or not v['source_account_hash'] or v['bank_transaction_id']==v['original_bank_id']:raise ValueError('Para distinguir dos salidas similares indique el payout original, la cuenta de origen y los dos identificadores bancarios distintos, respaldados por evidencia.')
                if any(p.id!=original.id for p in matches):raise ValueError('Hay otras salidas similares que requieren revisión antes de añadir otra.')
                old_key=fingerprint(['bank',v['source_account_hash'],v['original_bank_id']])
                identity_existing=db.scalar(select(Identity).where(Identity.payout_root_id==duplicate_root))
                collision=db.scalar(select(Identity).where(Identity.bank_key==old_key))
                if (identity_existing and identity_existing.bank_key!=old_key) or (collision and collision.payout_root_id!=duplicate_root):raise ValueError('La identificación del movimiento original no coincide.')
        return root,duplicate_root,identity_existing

    def preview(self,db,settlement_id,**inputs):
        settlement,b=self.context(db,settlement_id);v=self.normalized(db,settlement,**inputs)
        root,duplicate_root,_=self.evaluate(db,settlement,b,v)
        amount=Decimal(v['amount']);loss=amount if v['source_kind']=='payout' and not v['receipt_accredited'] else ZERO
        extra=Decimal(v['allocations'].get(str(settlement.owner_id),'0')) if v['source_kind']=='extraordinary' else ZERO
        cash_after=b['cash_used']+extra
        impact=dict(transferred=v['amount'],paid_before=str(b['paid']),paid_after=str(b['paid']-loss),remaining_before=str(b['remaining']),remaining_after=str(b['remaining']+loss),available_before=str(b['available']),available_after=str(ZERO if b['payout_blockers'] or not v['allocations'] else max(ZERO,b['owner_funds']-cash_after)),pending_recovery=str(ZERO if v['receipt_accredited'] else amount),deficit=str(max(ZERO,cash_after-b['owner_funds'])),allocations=v['allocations'],blocked=not v['allocations'])
        impact['funding_effects']={}
        if v['source_kind']=='extraordinary':
            for owner,part in v['allocations'].items():
                other=db.scalar(select(OwnerSettlement).where(OwnerSettlement.owner_id==int(owner),OwnerSettlement.status=='closed').order_by(OwnerSettlement.id))
                if other:
                    ob=self.balances.summary(db,other)
                else:
                    from backend.services.owner_transfer_state import incident_effects
                    ob=dict(owner_funds=ZERO,cash_used=incident_effects(db,int(owner),0)['extra'])
                net=ob['owner_funds']-ob['cash_used']-Decimal(part)
                impact['funding_effects'][owner]=dict(amount=part,available=str(max(ZERO,net)),deficit=str(max(ZERO,-net)))
        # Include all transfer identities to detect a concurrent outflow, even for another owner.
        identities=[raw(x) for x in db.scalars(select(Identity).order_by(Identity.id))]
        state=dict(incident_state=b['incident_state'],identities=identities,payouts=[raw(x) for x in b['all_payouts']],corrections=[raw(x) for x in b['operations']],returns=[raw(x) for x in b['all_returns']],closed=[raw(x) for x in db.scalars(select(OwnerSettlement).where(OwnerSettlement.status=='closed').order_by(OwnerSettlement.id))],all_payouts=[raw(x) for x in db.scalars(select(OwnerPayout).order_by(OwnerPayout.id))],values=v,impact=impact)
        return dict(settlement=settlement,balance=b,values=v,impact=impact,root=root,duplicate_root=duplicate_root,fingerprint=fingerprint(state))

    def confirm(self,db,settlement_id,*,request_key,expected,confirmed=False,operator_id=None,**inputs):
        if confirmed is not True:raise ValueError('Confirme expresamente el impacto revisado.')
        key=request_id(request_key)
        with financial_transaction(db):
            settlement,_=self.context(db,settlement_id);v=self.normalized(db,settlement,**inputs);digest=fingerprint([settlement_id,v])
            prior=db.get(Operation,key)
            if prior:
                if prior.fingerprint!=digest:raise ValueError('Clave ya utilizada con otros datos.')
                return db.get(Incident,prior.incident_id)
            review=self.preview(db,settlement_id,**inputs)
            if review['fingerprint']!=expected:raise ValueError('Los datos han cambiado. Revise nuevamente.')
            incident=Incident(settlement_id=settlement_id,intended_owner_id=settlement.owner_id,source_kind=v['source_kind'],payout_root_id=review['root'],duplicate_of_root_id=review['duplicate_root'],kind=v['kind'],affected_amount=money(v['amount']),recipient_owner_id=v['recipient_owner_id'],recipient_description=safe(v['recipient_description']) or None,receipt_accredited=v['receipt_accredited'],reason=safe(v['reason']),evidence=safe(v['evidence']))
            db.add(incident);db.flush()
            if v['source_kind']=='extraordinary':
                out=Outflow(incident_id=incident.id,amount=money(v['amount']),effective_date=date.fromisoformat(v['effective_date']),source_account_hash=v['source_account_hash'],source_account_suffix=v['source_account_suffix'],destination_hash=v['destination_hash'],destination_suffix=v['destination_suffix'],reference=safe(v['reference']),bank_transaction_id=v['bank_transaction_id'])
                db.add(out);db.flush()
                db.add(Identity(outflow_id=out.id,bank_key=self.bank_key(v),source_account_hash=v['source_account_hash'],bank_transaction_id=v['bank_transaction_id']))
                if review['duplicate_root'] and not db.scalar(select(Identity.id).where(Identity.payout_root_id==review['duplicate_root'])):
                    db.add(Identity(payout_root_id=review['duplicate_root'],bank_key=fingerprint(['bank',v['source_account_hash'],v['original_bank_id']]),source_account_hash=v['source_account_hash'],bank_transaction_id=v['original_bank_id']))
            elif v['bank_transaction_id'] and not db.scalar(select(Identity.id).where(Identity.payout_root_id==review['root'])):
                db.add(Identity(payout_root_id=review['root'],bank_key=self.bank_key(v),source_account_hash=v['source_account_hash'],bank_transaction_id=v['bank_transaction_id']))
            state=dict(allocations=v['allocations'],scope=v['scope'],impact=review['impact'])
            db.add(Operation(request_key=key,incident_id=incident.id,kind='register',reason=safe(v['reason']),operator_id=str(operator_id)[:160] if operator_id else None,before_state={},after_state=state,fingerprint=digest,reviewed_state=expected))
            db.flush();self.balances.summary(db,settlement)
        return incident

    def attribution_preview(self,db,incident_id,*,allocations=None,reason=None):
        detail=self.detail(db,incident_id);incident=detail['incident']
        if incident.source_kind!='extraordinary' or detail['state'].get('allocations'):raise ValueError('Solo se atribuyen salidas extraordinarias pendientes; no se redistribuyen fondos ya atribuidos.')
        if not str(reason or '').strip():raise ValueError('Motivo de atribución obligatorio.')
        allocation=self.allocations(db,allocations or {},incident.affected_amount)
        if not allocation:raise ValueError('Indique la atribución completa.')
        # Recompute every affected owner's cash position, including owners without settlements.
        effects={}
        for owner in allocation:
            settlement=db.scalar(select(OwnerSettlement).where(OwnerSettlement.owner_id==int(owner),OwnerSettlement.status=='closed').order_by(OwnerSettlement.id))
            if settlement:b=self.balances.summary(db,settlement)
            else:
                from backend.services.owner_transfer_state import incident_effects
                b=dict(owner_funds=ZERO,cash_used=incident_effects(db,int(owner),0)['extra'],available=ZERO)
            net=b['owner_funds']-b['cash_used']-Decimal(allocation[owner])
            effects[owner]=dict(available_before=str(b['available']),available_after=str(max(ZERO,net)),deficit=str(max(ZERO,-net)))
        state=dict(history=[raw(x) for x in detail['history']],all_state=detail['balance']['incident_state'],allocations=allocation,reason=reason,effects=effects,payouts=[raw(x) for x in db.scalars(select(OwnerPayout).order_by(OwnerPayout.id))],closed=[raw(x) for x in db.scalars(select(OwnerSettlement).where(OwnerSettlement.status=='closed').order_by(OwnerSettlement.id))])
        return dict(**detail,allocations=allocation,reason=reason,effects=effects,fingerprint=fingerprint(state))

    def attribute(self,db,incident_id,*,allocations,reason,request_key,expected,confirmed=False,operator_id=None):
        if confirmed is not True:raise ValueError('Confirme la atribución revisada.')
        key=request_id(request_key)
        with financial_transaction(db):
            digest=fingerprint(['attribute',incident_id,allocations,reason]);prior=db.get(Operation,key)
            if prior:
                if prior.fingerprint!=digest:raise ValueError('Clave ya utilizada con otros datos.')
                return db.get(Incident,incident_id)
            review=self.attribution_preview(db,incident_id,allocations=allocations,reason=reason)
            if review['fingerprint']!=expected:raise ValueError('Los fondos han cambiado. Revise nuevamente.')
            db.add(Operation(request_key=key,incident_id=incident_id,kind='attribute',reason=safe(reason),operator_id=str(operator_id)[:160] if operator_id else None,before_state=review['state'],after_state=dict(allocations=review['allocations'],scope=[],impact=review['effects']),fingerprint=digest,reviewed_state=expected));db.flush()
        return db.get(Incident,incident_id)
