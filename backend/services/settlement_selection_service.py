"""Read-only property selection and atomic creation of individual drafts."""
from uuid import UUID, uuid5
from decimal import Decimal

from sqlalchemy import select

from backend.models.owner import Owner
from backend.models.property import Property
from backend.models.property_ownership import PropertyOwnership
from backend.models.owner_settlement import OwnerSettlement
from backend.services.expense_service import fingerprint
from backend.services.financial_transaction import financial_transaction
from backend.services.owner_settlement_service import OwnerSettlementService


class SettlementSelectionService:
    def __init__(self):
        self.individual = OwnerSettlementService()

    def catalog(self, db, start, end, property_ids=None):
        if start >= end:
            raise ValueError('Revise el periodo de liquidación.')
        query = select(Property).order_by(Property.name, Property.id)
        if property_ids is not None:
            query = query.where(Property.id.in_(property_ids))
        properties = list(db.scalars(query))
        owners = {o.id: o.name for o in db.scalars(select(Owner))}
        relations = list(db.scalars(select(PropertyOwnership)))
        result = []
        for prop in properties:
            errors = []
            try:
                current = self.individual.ownership(db, prop.id, start, end)
            except ValueError as exc:
                current = []
                errors.append(str(exc))
            # Include historical recipients: an old, late receipt must not be
            # attributed to today's owner. The domain preview resolves each source.
            candidates = {r.owner_id for r in relations if r.property_id == prop.id
                          and (r.active or r.effective_until is not None)
                          and (r.effective_from is None or r.effective_from < end)}
            entries = []
            for owner_id in sorted(candidates):
                view = self.individual.preview(db, owner_id, start, end, [prop.id])
                errors.extend(view['errors'])
                movement_rows = [r for r in view['rows'] if r['kind'] != 'prior_balance']
                if movement_rows or any(r.owner_id == owner_id for r in current):
                    property_totals = dict(view['totals'])
                    funds = Decimal(property_totals['funds_balance']) - Decimal(property_totals['prior_balance'])
                    property_totals.update(funds_balance=str(funds), payout_due=str(max(Decimal('0.00'), funds)),
                                           carry_forward=str(min(Decimal('0.00'), funds)), prior_balance='0.00',
                                           economic_balance=property_totals['period_balance'],
                                           manager_credit=str(max(Decimal('0.00'), -funds)))
                    entries.append(dict(owner_id=owner_id, name=owners[owner_id],
                        percentage=next((str(r.ownership_percentage) for r in current if r.owner_id == owner_id), None),
                        view=view, totals=property_totals, has_movements=bool(view['rows'])))
            state = 'review' if errors else 'ready' if any(e['has_movements'] for e in entries) else 'empty'
            result.append(dict(id=prop.id, name=prop.name, owners=entries,
                               errors=list(dict.fromkeys(errors)), state=state))
        return result

    def preview(self, db, start, end, property_ids):
        property_ids = sorted(set(int(v) for v in property_ids))
        if not property_ids:
            raise ValueError('Seleccione al menos una finca.')
        groups = self.catalog(db, start, end, property_ids)
        if len(groups) != len(property_ids):
            raise ValueError('Una finca seleccionada ya no existe.')
        errors, resolved = [], {}
        for group in groups:
            errors.extend(f"{group['name']}: {error}" for error in group['errors'])
            for entry in group['owners']:
                if entry['has_movements']:
                    resolved.setdefault(entry['owner_id'], {'name': entry['name'], 'properties': []})['properties'].append(group['id'])
        views = []
        for owner_id, entry in sorted(resolved.items()):
            view = self.individual.preview(db, owner_id, start, end, entry['properties'])
            errors.extend(view['errors'])
            if view['rows']:
                views.append(dict(name=entry['name'], view=view))
        payload = dict(start=str(start), end=str(end), property_ids=property_ids,
                       groups=groups, individuals=views, errors=list(dict.fromkeys(errors)))
        return {**payload, 'fingerprint': fingerprint(payload)}

    def save_drafts(self, db, start, end, property_ids, expected, request_key):
        batch_key = str(UUID(request_key))
        with financial_transaction(db):
            # Stored batch fingerprint enables idempotent retries even after a
            # resulting draft has been closed and consumed its sources.
            existing = [row for row in db.scalars(select(OwnerSettlement))
                        if row.selection.get('selection_request') == batch_key]
            if existing:
                if any(row.selection.get('selection_fingerprint') != expected for row in existing):
                    raise ValueError('Solicitud ya utilizada con otros datos.')
                return existing
            preview = self.preview(db, start, end, property_ids)
            if preview['fingerprint'] != expected:
                raise ValueError('Los datos han cambiado. Previsualice nuevamente las fincas.')
            if preview['errors'] or not preview['individuals']:
                raise ValueError('Revise las incidencias; no se ha creado ningún borrador.')
            created = []
            for entry in preview['individuals']:
                view = entry['view']
                row = OwnerSettlement(owner_id=view['owner_id'], period_start=start, period_end=end,
                    selection={'properties': view['property_ids'], 'excluded': [],
                               'selection_request': batch_key, 'selection_fingerprint': expected},
                    fingerprint=view['fingerprint'], snapshot=view, status='draft',
                    request_key=str(uuid5(UUID(batch_key), str(view['owner_id']))))
                db.add(row)
                created.append(row)
            db.flush()
        return created
