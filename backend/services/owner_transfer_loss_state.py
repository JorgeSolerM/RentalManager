"""Informational loss projection, deliberately without cash or debt effects."""
from decimal import Decimal
from sqlalchemy import select
from backend.models.owner_transfer_regularization import OwnerTransferRegularizationOperation as Operation
from backend.models.owner_transfer_recovery import OwnerTransferRecovery

def loss_state(db, incident):
    rows=list(db.scalars(select(Operation).where(Operation.incident_id==incident.id).order_by(Operation.id)))
    recognized=[r for r in rows if r.kind=='recognize']
    assigned={r.loss_id:r for r in rows if r.kind=='responsibility'}
    recoveries=list(db.scalars(select(OwnerTransferRecovery).where(OwnerTransferRecovery.incident_id==incident.id)))
    received=sum((r.amount for r in recoveries),Decimal('0'))
    outstanding=incident.affected_amount-received
    total=sum((r.amount for r in recognized),Decimal('0'))
    later=any(received>Decimal(r.before_state['recovered']) for r in recognized)
    responsibilities=[dict(loss_id=r.id,amount=str(r.amount),responsible=assigned.get(r.id,r).responsible,
        owner_id=assigned.get(r.id,r).responsible_owner_id,agreement=assigned.get(r.id,r).agreement) for r in recognized]
    return dict(affected=str(incident.affected_amount),recovered=str(received),outstanding=str(outstanding),recognized=str(total),
        without_loss_recognition=str(max(Decimal('0'),outstanding-total)),overlap=str(max(Decimal('0'),total-outstanding)),
        later_recovery_pending=later,responsibilities=responsibilities,operations=rows)
