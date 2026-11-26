"""Projection only: compensation never changes banking funds or frozen settlements."""
from decimal import Decimal
from sqlalchemy import select
from backend.models.owner_loss_compensation import OwnerLossCompensationAuthorization as Authorization, OwnerLossCompensationApplication as Application
from backend.models.owner_transfer_recovery import OwnerTransferRecovery

ZERO = Decimal('0')

def compensation_state(db, owner_id, settlement_id):
    auth = list(db.scalars(select(Authorization).where(Authorization.owner_id == owner_id).order_by(Authorization.id)))
    apps = list(db.scalars(select(Application).where(Application.owner_id == owner_id).order_by(Application.id)))
    recoveries = list(db.scalars(select(OwnerTransferRecovery).where(OwnerTransferRecovery.incident_id.in_({a.incident_id for a in auth})).order_by(OwnerTransferRecovery.id)))
    current = [a for a in apps if a.settlement_id == settlement_id]
    blockers = []
    for a in auth:
        used = [x for x in apps if x.authorization_id == a.id]
        # IDs captured under the same write lock avoid ambiguous equal timestamps.
        prior = set(a.after_state['recovery_ids'])
        if a.owner_id == owner_id and used and any(r.incident_id == a.incident_id and r.id not in prior for r in recoveries):
            blockers.append(f'Acuerdo #{a.id}: Regularización posterior pendiente. Fondos del propietario bloqueados hasta la subfase 4.4.')
    raw = lambda x: {c.name: getattr(x, c.name) for c in x.__table__.columns}
    return dict(compensated=sum((x.amount for x in current), ZERO), applications=current,
                authorizations=auth, all_applications=apps, blockers=blockers,
                fingerprint_state=[*[raw(a) for a in auth], *[raw(a) for a in apps]])

def document_compensations(db, settlement):
    state = compensation_state(db, settlement.owner_id, settlement.id)
    auth = {a.id: a for a in state['authorizations']}
    return [dict(id=a.id, settlement_id=a.settlement_id, incident_id=auth[a.authorization_id].incident_id,
                 loss_id=auth[a.authorization_id].loss_id, agreement=auth[a.authorization_id].agreement_reference,
                 amount=str(a.amount), date=str(a.created_at), informative=a.settlement_id != settlement.id)
            for a in state['all_applications'] if a.owner_id == settlement.owner_id and
            (a.settlement_id == settlement.id or a.created_at <= settlement.closed_at)]
