"""Read-only grouping of resolved sources; never chooses an ambiguous expense.

Historical terms must already have been resolved by each source's economic
period. This planner never queries current terms or substitutes their IDs.
"""
from copy import deepcopy
from hashlib import sha256
import json


def group_fee_sources(owner_id, sources, expense_assignments=None, *, property_signatures=None):
    """Single planner for both unit callers and the integrated settlement flow.

    Explicit property signatures are only fallbacks for expense/non-fee sources
    without an income group. The caller resolves their historical terms first.
    """
    assignments = dict(expense_assignments or {})
    property_signatures = dict(property_signatures or {})
    rows = deepcopy(list(sources))
    keys = [row['key'] for row in rows]
    if len(set(keys)) != len(keys):
        raise ValueError('Una fuente no puede aparecer dos veces.')
    if any(row['owner_id'] != owner_id for row in rows):
        raise ValueError('No se agrupan fuentes de propietarios diferentes.')
    groups, expenses = {}, []

    def ensure_group(signature):
        if not signature or not signature.get('digest') or not signature.get('fields'):
            raise ValueError('Falta la firma fiscal explícita de una fuente.')
        digest = signature['digest']
        canonical = json.dumps(signature['fields'], sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        if digest != sha256(canonical.encode('utf-8')).hexdigest():
            raise ValueError('La firma fiscal no corresponde al contenido de la fuente.')
        group = groups.setdefault(digest, dict(signature=signature, sources=[], property_ids=set()))
        if group['signature']['fields'] != signature['fields']:
            raise ValueError('Firma incoherente entre fuentes.')
        return group

    for row in rows:
        if row['kind'] not in {'income', 'expense'}:
            raise ValueError('Fuente de liquidación no soportada.')
        signature = row.get('fiscal_snapshot', {}).get('fee_signature')
        if row['kind'] == 'expense' or not signature:
            expenses.append(row)
            continue
        group = ensure_group(signature)
        group['sources'].append(row)
        group['property_ids'].add(row['property_id'])
    known_expenses = {row['key'] for row in expenses}
    if set(assignments) - known_expenses:
        raise ValueError('La selección de gastos contiene fuentes desconocidas.')
    issues = []
    for row in expenses:
        candidates = sorted(key for key, group in groups.items() if row['property_id'] in group['property_ids'])
        if not candidates and row['property_id'] in property_signatures:
            signature = property_signatures[row['property_id']]
            ensure_group(signature)['property_ids'].add(row['property_id'])
            candidates = [signature['digest']]
        chosen = assignments.get(row['key']) or None
        if chosen and chosen not in candidates:
            raise ValueError('El gasto no corresponde a la liquidación elegida.')
        if chosen is None and len(candidates) == 1:
            chosen = candidates[0]
        if chosen is None:
            issues.append(dict(source_key=row['key'], candidates=candidates,
                message='Seleccione en qué liquidación incluir este gasto.' if candidates else
                        'Falta un grupo fiscal explícito para esta finca; revise sus condiciones.'))
        else:
            groups[chosen]['sources'].append(row)
    result = []
    for digest, group in groups.items():
        if not group['sources']:
            continue
        group['sources'].sort(key=lambda row: (row['date'], bool(row.get('reversal_of')),
                                              row.get('source_id', 0), row['key']))
        result.append(dict(owner_id=owner_id, signature=group['signature'],
            group_key=digest, sources=group['sources'], property_ids=sorted(group['property_ids'])))
    result.sort(key=lambda group: (group['sources'][0]['date'], group['group_key']))
    return dict(groups=result, issues=issues)
