"""Audited non-cash consumption of an explicit owner agreement."""
import unicodedata
from decimal import Decimal
from sqlalchemy import select, inspect, text
from backend.models.owner_loss_compensation import OwnerLossCompensationAuthorization as Authorization, OwnerLossCompensationApplication as Application
from backend.models.owner_transfer_regularization import OwnerTransferRegularizationOperation as Loss
from backend.models.owner_settlement import OwnerSettlement
from backend.services.owner_transfer_regularization_service import OwnerTransferRegularizationService
from backend.services.owner_transfer_recovery_service import OwnerTransferRecoveryService
from backend.services.owner_payout_balance_service import OwnerPayoutBalanceService
from backend.services.owner_transfer_incident_service import safe
from backend.services.expense_service import fingerprint, request_id
from backend.services.settlement_money import money
from backend.services.financial_transaction import financial_transaction


class OwnerLossCompensationService:
    def form(self, db, incident_id):
        view = OwnerTransferRegularizationService().form(db, incident_id)
        # The responsible owner can differ from the original settlement owner.
        auth = list(db.scalars(select(Authorization).where(Authorization.incident_id == incident_id).order_by(Authorization.id)))
        apps = list(db.scalars(select(Application).where(Application.authorization_id.in_({a.id for a in auth})).order_by(Application.id)))
        used = {a.id: sum((x.amount for x in apps if x.authorization_id == a.id), Decimal('0')) for a in auth}
        owner_ids = {x['owner_id'] for x in view['loss']['responsibilities'] if x['responsible'] == 'owner'}
        settlements = list(db.scalars(select(OwnerSettlement).where(OwnerSettlement.status == 'closed', OwnerSettlement.owner_id.in_(owner_ids)).order_by(OwnerSettlement.id)))
        return dict(**view, authorizations=auth, applications=apps, used=used, settlements=settlements)

    def normalized(self, **v):
        mode = v.get('mode')
        if mode not in ('authorize', 'apply'): raise ValueError('Operación no válida.')
        amount = money(v.get('amount'))
        if amount <= 0: raise ValueError('Importe positivo obligatorio.')
        texts = {k: safe(str(v.get(k) or '').strip()) for k in ('reason', 'evidence')}
        if any(not t or len(t) > 2000 for t in texts.values()): raise ValueError('Motivo y evidencia obligatorios, hasta 2000 caracteres.')
        try:
            result = dict(mode=mode, amount=str(amount), **texts)
            if mode == 'authorize':
                ids = v.get('settlement_ids', [])
                if isinstance(ids, str): ids = ids.split(',')
                ids = sorted(set(int(x) for x in ids))
                reference = safe(str(v.get('agreement_reference') or '').strip())
                if not ids or not reference or len(reference) > 160 or v.get('authorized') is not True:
                    raise ValueError('Acuerdo, liquidaciones comprendidas y autorización expresa de compensación obligatorios.')
                result.update(loss_id=int(v.get('loss_id')), agreement_reference=reference, settlement_ids=ids, authorized=True)
            else: result.update(authorization_id=int(v.get('authorization_id')), settlement_id=int(v.get('settlement_id')))
            return result
        except (TypeError, ValueError) as exc:
            raise ValueError(str(exc) if isinstance(exc, ValueError) and 'obligatorios' in str(exc) else 'Identificadores y alcance del acuerdo no válidos.') from None

    def preview(self, db, incident_id, **inputs):
        v = self.normalized(**inputs); amount = Decimal(v['amount']); view = self.form(db, incident_id)
        if view['loss']['later_recovery_pending']:
            raise ValueError('Regularización posterior pendiente: revise la recuperación posterior a la pérdida antes de compensar.')
        if v['mode'] == 'authorize':
            loss = db.get(Loss, v['loss_id'])
            if loss is None or loss.incident_id != incident_id or loss.kind != 'recognize': raise ValueError('Pérdida reconocida no válida.')
            responsible = db.scalar(select(Loss).where(Loss.loss_id == loss.id)) or loss
            if responsible.responsible != 'owner' or not responsible.agreement.strip(): raise ValueError('Se requiere responsabilidad del propietario con acuerdo documentado.')
            owner_id = responsible.responsible_owner_id
            if amount > responsible.amount: raise ValueError('La autorización supera la responsabilidad reconocida.')
            agreement_key = fingerprint(' '.join(unicodedata.normalize('NFKC', v['agreement_reference']).casefold().split()))
            if db.scalar(select(Authorization.id).where((Authorization.loss_id == loss.id) | (Authorization.agreement_key == agreement_key))):
                raise ValueError('La pérdida o el acuerdo ya tienen una autorización. No se duplican acuerdos globales.')
            settlements = [db.get(OwnerSettlement, x) for x in v['settlement_ids']]
            authorized = amount; used = Decimal('0')
        else:
            authorization = db.get(Authorization, v['authorization_id'])
            if authorization is None or authorization.incident_id != incident_id: raise ValueError('Autorización no válida para esta incidencia.')
            loss = db.get(Loss, authorization.loss_id); responsible = db.get(Loss, authorization.responsibility_id)
            owner_id = authorization.owner_id
            if responsible.responsible != 'owner' or responsible.responsible_owner_id != owner_id or not responsible.agreement.strip(): raise ValueError('Responsabilidad incompatible.')
            if v['settlement_id'] not in authorization.settlement_ids: raise ValueError('La liquidación no está comprendida en el acuerdo.')
            settlements = [db.get(OwnerSettlement, v['settlement_id'])]
            authorized = authorization.amount; used = view['used'][authorization.id]
            if amount > authorized - used: raise ValueError('Importe superior al acuerdo disponible; no puede aplicarse dos veces.')
            agreement_key = authorization.agreement_key
        if not settlements or any(s is None or s.status != 'closed' or s.owner_id != owner_id for s in settlements):
            raise ValueError('Las liquidaciones deben estar cerradas y pertenecer al mismo propietario responsable.')
        if str(owner_id) not in view['state'].get('allocations', {}): raise ValueError('Fondos pendientes de atribución: acredite el propietario afectado.')
        if any(s.selection.get('billing') for s in settlements): raise ValueError('Liquidación con circuito de facturación: compensación incompatible en esta subfase.')
        # Preserve the existing compatibility guard; this does not operate on
        # the fiscal module or require its migration.
        if inspect(db.connection()).has_table('fee_compensations'):
            for s in settlements:
                if db.execute(text('SELECT 1 FROM fee_compensations WHERE settlement_id=:sid LIMIT 1'), {'sid': s.id}).first():
                    raise ValueError('Existen compensaciones incompatibles vinculadas a esta liquidación; requiere revisión específica.')
        balances = [OwnerPayoutBalanceService().summary(db, s) for s in settlements]
        for b in balances:
            if b['payout_blockers']: raise ValueError(' '.join(b['payout_blockers']))
        if OwnerPayoutBalanceService().pending_returns(db, owner_id): raise ValueError('Hay devoluciones pendientes de liquidar.')
        before_pending = sum((b['remaining'] for b in balances), Decimal('0'))
        if v['mode'] == 'apply' and amount > before_pending: raise ValueError('La compensación supera la obligación pendiente.')
        # No cash movement, even when cash is insufficient or the owner has a deficit.
        impact = dict(authorized=str(authorized), applied=str(used), available_authorization=str(authorized-used),
                      remaining_before=str(before_pending), adjustment=str(amount if v['mode']=='apply' else 0),
                      remaining_after=str(before_pending-(amount if v['mode']=='apply' else 0)),
                      available_before=str(balances[0]['available']), available_after=str(balances[0]['available']), deficit=str(balances[0]['deficit']))
        rv = OwnerTransferRecoveryService().form(db, incident_id)
        economic = OwnerTransferRecoveryService().state(db, rv)
        raw = lambda x: {c.name: getattr(x, c.name) for c in x.__table__.columns}
        return dict(**view, values=v, impact=impact, owner_id=owner_id, responsibility_id=responsible.id,
                    agreement_key=agreement_key, recovery_ids=[r.id for r in rv['recoveries']],
                    fingerprint=fingerprint([economic, [raw(s) for s in settlements], raw(responsible), v, impact]))

    def confirm(self, db, incident_id, *, request_key, expected, confirmed=False, operator_id=None, **inputs):
        if confirmed is not True: raise ValueError('Confirme expresamente el acuerdo y el impacto sin movimiento bancario.')
        v = self.normalized(**inputs); key = request_id(request_key); digest = fingerprint([incident_id, v])
        model = Authorization if v['mode'] == 'authorize' else Application
        with financial_transaction(db):
            old = db.scalar(select(model).where(model.request_key == key))
            if old:
                if old.fingerprint != digest: raise ValueError('Clave utilizada con otros datos.')
                return old
            view = self.preview(db, incident_id, **inputs)
            if expected != view['fingerprint']: raise ValueError('La vista previa está desactualizada; vuelva a revisar.')
            impact = view['impact']
            before = dict(authorized=impact['authorized'] if model is Application else '0',
                          applied=impact['applied'], available_authorization=impact['available_authorization'] if model is Application else '0',
                          remaining=impact['remaining_before'], available=impact['available_before'], deficit=impact['deficit'])
            applied_after = Decimal(impact['applied']) + (Decimal(v['amount']) if model is Application else Decimal('0'))
            after = dict(authorized=impact['authorized'], applied=str(applied_after),
                         available_authorization=str(Decimal(impact['authorized'])-applied_after),
                         remaining=impact['remaining_after'], available=impact['available_after'], deficit=impact['deficit'],
                         recovery_ids=view['recovery_ids'])
            common = dict(amount=Decimal(v['amount']), reason=v['reason'], evidence=v['evidence'],
                          operator_id=safe(str(operator_id))[:160] if operator_id else None,
                          before_state=before, after_state=after,
                          request_key=key, fingerprint=digest, reviewed_state=expected, owner_id=view['owner_id'])
            if model is Authorization:
                row = model(**common, incident_id=incident_id, loss_id=v['loss_id'], responsibility_id=view['responsibility_id'],
                            agreement_reference=v['agreement_reference'], agreement_key=view['agreement_key'], settlement_ids=v['settlement_ids'])
            else: row = model(**common, authorization_id=v['authorization_id'], settlement_id=v['settlement_id'])
            db.add(row); db.flush()
        return row
