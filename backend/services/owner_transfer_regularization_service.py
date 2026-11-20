"""Phase 4.1: recognition and responsibility, never application to settlements."""
import unicodedata
from decimal import Decimal
from sqlalchemy import select
from backend.models.owner_transfer_regularization import OwnerTransferRegularizationOperation as Operation
from backend.services.owner_transfer_incident_service import OwnerTransferIncidentService, safe
from backend.services.owner_transfer_loss_state import loss_state
from backend.services.owner_transfer_recovery_service import OwnerTransferRecoveryService
from backend.services.expense_service import fingerprint,request_id
from backend.services.settlement_money import money
from backend.services.financial_transaction import financial_transaction

def projection(state):
    return {k:v for k,v in state.items() if k!='operations'}

class OwnerTransferRegularizationService:
    def form(self,db,incident_id):
        context=OwnerTransferIncidentService().detail(db,incident_id)
        return dict(**context,loss=loss_state(db,context['incident']))

    def normalized(self,**v):
        kind=str(v.get('kind','recognize'))
        if kind not in ('recognize','responsibility'):raise ValueError('Operación no válida.')
        responsible=str(v.get('responsible') or '')
        if responsible not in ('pending','manager','owner'):raise ValueError('Indique quién asume la responsabilidad o si queda pendiente.')
        texts={k:safe(str(v.get(k) or '').strip()) for k in ('reason','evidence','evidence_reference','agreement')}
        if any(not texts[k] for k in ('reason','evidence','evidence_reference')):raise ValueError('Motivo, evidencia y referencia documental obligatorios.')
        if any(len(x)>2000 for x in texts.values()) or len(texts['evidence_reference'])>160:raise ValueError('Texto demasiado largo.')
        try:
            loss_id=int(v['loss_id']) if v.get('loss_id') else None
            owner=int(v['responsible_owner_id']) if v.get('responsible_owner_id') else None
        except (ValueError,TypeError):raise ValueError('Identificador no válido.') from None
        if (kind=='responsibility')!=(loss_id is not None):raise ValueError('Seleccione la pérdida pendiente de responsabilidad.')
        if responsible=='owner':
            if not owner or not texts['agreement'] or v.get('authorized') is not True:raise ValueError('Se requiere propietario, acuerdo expreso y confirmación de su autorización.')
        elif owner:raise ValueError('No atribuya a un propietario una responsabilidad del gestor o pendiente.')
        if kind=='responsibility' and responsible=='pending':raise ValueError('La responsabilidad ya está pendiente.')
        amount=money(v.get('amount'))
        if amount<=0:raise ValueError('Importe positivo obligatorio.')
        return dict(kind=kind,loss_id=loss_id,amount=str(amount),responsible=responsible,responsible_owner_id=owner,
                    authorized=responsible=='owner',**texts)

    def preview(self,db,incident_id,**inputs):
        v=self.normalized(**inputs);view=self.form(db,incident_id);state=view['loss'];amount=Decimal(v['amount'])
        if view['incident'].receipt_accredited:raise ValueError('La recepción por el propietario está acreditada; no se presume una pérdida por la cuenta utilizada.')
        ref=' '.join(unicodedata.normalize('NFKC',v['evidence_reference']).casefold().split())
        key=fingerprint([incident_id,ref]) if v['kind']=='recognize' else None
        if v['kind']=='recognize':
            if state['later_recovery_pending']:raise ValueError('Existe una recuperación posterior a una pérdida: regularización pendiente de la subfase 4.4.')
            if amount>Decimal(state['without_loss_recognition']):raise ValueError('El importe supera el saldo sin reconocer como pérdida; no se reconoce dos veces.')
            if db.scalar(select(Operation.id).where(Operation.incident_id==incident_id,Operation.recognition_key==key)):raise ValueError('La referencia documental de esta pérdida ya está registrada.')
        else:
            original=db.get(Operation,v['loss_id'])
            if not original or original.incident_id!=incident_id or original.kind!='recognize' or original.responsible!='pending':raise ValueError('La pérdida no está pendiente de asignación en esta incidencia.')
            if original.amount!=amount:raise ValueError('La asignación debe conservar íntegro el importe reconocido.')
            if db.scalar(select(Operation.id).where(Operation.loss_id==original.id)):raise ValueError('Esta pérdida ya tiene responsabilidad asignada.')
        if v['responsible']=='owner':
            allocations=view['state'].get('allocations',{})
            if str(v['responsible_owner_id']) not in allocations:raise ValueError('El propietario debe pertenecer a la atribución acreditada de los fondos; resuelva antes la atribución.')
            used=sum((Decimal(x['amount']) for x in state['responsibilities'] if x['owner_id']==v['responsible_owner_id']),Decimal('0'))
            recovery_view=OwnerTransferRecoveryService().form(db,incident_id)
            restored=sum((Decimal(parts.get(str(v['responsible_owner_id']),'0')) for rid,parts in recovery_view['recovery_allocations'].items() if any(r.id==rid for r in recovery_view['recoveries'])),Decimal('0'))
            if used+amount>Decimal(allocations[str(v['responsible_owner_id'])])-restored:raise ValueError('La responsabilidad supera los fondos atribuidos a ese propietario.')
        before=projection(state);after=dict(before)
        responsibilities=[dict(x) for x in before['responsibilities']]
        entry=dict(loss_id=v['loss_id'],amount=v['amount'],responsible=v['responsible'],owner_id=v['responsible_owner_id'],agreement=v['agreement'])
        if v['kind']=='recognize':
            after['recognized']=str(Decimal(state['recognized'])+amount)
            after['without_loss_recognition']=str(Decimal(state['without_loss_recognition'])-amount)
            responsibilities.append(entry)
        else:responsibilities=[entry if x['loss_id']==v['loss_id'] else x for x in responsibilities]
        after['responsibilities']=responsibilities
        unchanged={k:str(view['balance'][k]) for k in ('paid','remaining','available','deficit')}
        before['balances']=unchanged;after['balances']=dict(unchanged)
        recovery_view=OwnerTransferRecoveryService().form(db,incident_id)
        economic=OwnerTransferRecoveryService().state(db,recovery_view)
        return dict(**view,values=v,before=before,after=after,recognition_key=key,
            fingerprint=fingerprint([economic,[{c.name:getattr(r,c.name) for c in r.__table__.columns} for r in state['operations']],v,before,after]))

    def confirm(self,db,incident_id,*,request_key,expected,confirmed=False,operator_id=None,**inputs):
        if confirmed is not True:raise ValueError('Confirme expresamente el reconocimiento sin movimiento bancario ni descuento de liquidación.')
        v=self.normalized(**inputs);key=request_id(request_key);digest=fingerprint([incident_id,v])
        with financial_transaction(db):
            old=db.scalar(select(Operation).where(Operation.request_key==key))
            if old:
                if old.fingerprint!=digest:raise ValueError('Clave utilizada con otros datos.')
                return old
            view=self.preview(db,incident_id,**inputs)
            if expected!=view['fingerprint']:raise ValueError('La vista previa está desactualizada; vuelva a revisar.')
            row=Operation(incident_id=incident_id,kind=v['kind'],loss_id=v['loss_id'],amount=Decimal(v['amount']),
                responsible=v['responsible'],responsible_owner_id=v['responsible_owner_id'],agreement=safe(v['agreement']),
                reason=safe(v['reason']),evidence=safe(v['evidence']),evidence_reference=safe(v['evidence_reference']),
                recognition_key=view['recognition_key'],operator_id=str(operator_id)[:160] if operator_id else None,
                before_state=view['before'],after_state=view['after'],request_key=key,fingerprint=digest,reviewed_state=expected)
            db.add(row);db.flush()
        return row
