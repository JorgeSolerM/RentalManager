"""Read-only projection of immutable incident history, without bank recovery entries."""
from decimal import Decimal
from sqlalchemy import select
from backend.models.owner_transfer_incident import OwnerTransferIncident, OwnerTransferOutflow, OwnerTransferIncidentOperation

def incident_state(db):
    incidents=list(db.scalars(select(OwnerTransferIncident).order_by(OwnerTransferIncident.id)))
    outflows={x.incident_id:x for x in db.scalars(select(OwnerTransferOutflow).order_by(OwnerTransferOutflow.id))}
    operations=list(db.scalars(select(OwnerTransferIncidentOperation).order_by(OwnerTransferIncidentOperation.created_at,OwnerTransferIncidentOperation.request_key)))
    current={}
    # An attribution supersedes register regardless of equal UTC timestamps.
    for kind in ('register','attribute'):
        for op in operations:
            if op.kind==kind:current[op.incident_id]=op.after_state
    return incidents,outflows,current,operations

def incident_effects(db, owner_id, settlement_id):
    incidents,outflows,states,operations=incident_state(db)
    loss=Decimal('0');extra=Decimal('0');pending=Decimal('0');blockers=[];rows=[]
    for incident in incidents:
        state=states.get(incident.id,{})
        allocations=state.get('allocations',{})
        if incident.source_kind=='extraordinary':
            extra+=Decimal(allocations.get(str(owner_id),'0'))
            if not allocations:
                scope=state.get('scope',[])
                if not scope or owner_id in scope:blockers.append(f'Incidencia #{incident.id}: fondos pendientes de atribución.')
        if incident.intended_owner_id==owner_id:
            pending+=Decimal('0') if incident.receipt_accredited else incident.affected_amount
        if incident.settlement_id==settlement_id:
            if incident.source_kind=='payout' and not incident.receipt_accredited:loss+=incident.affected_amount
            rows.append(dict(id=incident.id,kind=incident.kind,source_kind=incident.source_kind,amount=str(incident.affected_amount),pending=str(Decimal('0') if incident.receipt_accredited else incident.affected_amount),review='Recepción acreditada' if incident.receipt_accredited else 'Requiere identificación' if incident.kind=='unknown_recipient' else 'Incidencia confirmada',funding='Atribuido' if allocations else 'Pendiente de atribución',allocations=allocations))
    raw=lambda x:{c.name:getattr(x,c.name) for c in x.__table__.columns}
    return dict(loss=loss,extra=extra,pending=pending,blockers=blockers,rows=rows,
        fingerprint_state=[*[raw(x) for x in incidents],*[raw(x) for x in outflows.values()],*[raw(x) for x in operations]])
