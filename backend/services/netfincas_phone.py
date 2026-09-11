"""Conservative phone candidates; syntax plausibility, not proof of ownership."""
import re
from backend.core.public_phone import phone_link_values
from backend.services.person_service import PersonService

PHONE_MAPPINGS = {
    'ALQ_INQUILINOS': [('FAX','mobile'),('TEL','phone')],
    'ALQ_INQUILINOS_H': [('FAX','mobile'),('TEL','phone')],
    'ALQ_PROPIETARIOS': [('FAX','mobile'),('TEL','phone')],
    'CONTACTOS': [('MOVIL','mobile'),('TELEFONO','phone'),('FAX','fax')],
    'EMPRESA': [('TELEFONO','phone'),('FAX','fax')],
    'PROVEEDORES': [('TELEFONO1','phone'),('TELEFONO2','phone'),('FAX','fax')],
}


def phone_value(value):
    value=PersonService._optional(value)
    if not value or len(value)>40 or not re.fullmatch(r'\+?[0-9() .-]+',value):return None
    if value.count('(')!=value.count(')'):return None
    links=phone_link_values(value)
    if not links:return None
    # Reject obviously non-telephone placeholders; no country is inferred.
    digits=links[0]
    if len(set(digits))==1:return None
    return dict(value=value,key=links[1][4:])


def phone_candidates(row, selected_field=None):
    candidates=[]
    fields=([('FAX','Móvil NetFincas'),('TEL','Teléfono NetFincas')]
        if row.get('_phone_mobile_field')=='FAX' else
        [('MOVIL','Móvil NetFincas'),('TEL','Teléfono NetFincas'),('FAX','FAX NetFincas (legacy)')])
    mapping=PHONE_MAPPINGS.get(row.get('_phone_entity'))
    roles=dict(mapping or [])
    if mapping:
        fields=[(field,{'mobile':'Móvil NetFincas','phone':'Teléfono NetFincas','fax':'Fax NetFincas'}[role]) for field,role in mapping]
    for field,label in fields:
        original=row.get(field)
        if not original or not original.strip():continue
        parsed=phone_value(original)
        candidates.append(dict(field=field,label=label,role=roles.get(field,'legacy'),original=original,valid=bool(parsed),
            normalized=parsed['value'] if parsed else None,key=parsed['key'] if parsed else None))
    valid=[c for c in candidates if c['valid'] and c['role']!='fax']
    conflict=len({c['key'] for c in valid})>1
    # Invalid populated higher-priority fields cannot be silently treated as empty.
    blocked=bool(valid and any(not c['valid'] for c in candidates[:candidates.index(valid[0])]))
    chosen=valid[0] if valid and not conflict and not blocked else None
    if selected_field:
        chosen=next((c for c in valid if c['field']==selected_field),None)
        if not chosen:raise ValueError('Candidato telefónico no válido; repita la revisión.')
    message=('NetFincas contiene varios teléfonos distintos. Revisar antes de completar.' if conflict else
        'Revisar teléfono: hay un campo prioritario informado que no parece válido.' if blocked else
        'Candidato móvil; requiere selección explícita.' if chosen and (chosen['role']=='mobile' or row.get('_phone_mobile_field')=='FAX') else
        'NetFincas guarda este número en FAX; parece un teléfono válido.' if chosen and chosen['field']=='FAX' else
        'Candidato único; requiere selección explícita.' if chosen else 'Sin candidato telefónico válido.')
    return dict(candidates=candidates,chosen=chosen,value=chosen['normalized'] if chosen else None,
        phone_candidates=[c for c in candidates if c['role']=='phone'],mobile_candidates=[c for c in candidates if c['role']=='mobile'],
        review=(conflict or blocked) and not selected_field,conflict=conflict,message=message)
