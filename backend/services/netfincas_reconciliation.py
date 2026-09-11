"""Explainable candidates and selective writes; no receipt/history importer."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
import re
import unicodedata
import uuid

from sqlalchemy import select, inspect
from backend.core.business_time import business_today
from backend.core.iban import is_valid_iban, mask_iban
from backend.models import Person, Booking, BookingParty, Property, Room, Owner, OwnerBankAccount, PropertyOwnership, BookingFinancialTerms
from backend.models.migration_audit import MigrationRun, MigrationAction
from backend.services.netfincas_source import digest
from backend.services.financial_transaction import financial_transaction
from backend.services.netfincas_phone import phone_candidates, phone_value
from backend.services.netfincas_address import address_line


PERSON_FIELDS = {'email': 'MAIL', 'phone': 'TEL', 'document_number': 'NIF',
    'address_line': 'address', 'postal_code': 'CP', 'city': 'POB', 'province': 'PROVINCIA', 'iban': 'iban'}
LABELS = {'email': 'Email', 'phone': 'Teléfono', 'document_number': 'Documento', 'address_line': 'Dirección',
    'postal_code': 'Código postal', 'city': 'Localidad', 'province': 'Provincia', 'country': 'País', 'iban': 'IBAN'}
MODELS = {'Person': Person, 'Booking': Booking, 'Owner': Owner, 'OwnerBankAccount': OwnerBankAccount,
    'PropertyOwnership': PropertyOwnership, 'BookingFinancialTerms': BookingFinancialTerms}


def normalize(v):
    return re.sub('[^a-z0-9]', '', unicodedata.normalize('NFKD', str(v or '')).encode('ascii', 'ignore').decode().lower())


def similarity(a, b):
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio() if a and b else 0


def source_date(v):
    if not v: return None
    months = dict(zip('JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC'.split(), range(1, 13)))
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', v): return date.fromisoformat(v)
        day, month, year = v.split()[0].upper().split('-')
        return date(int(year), months[month], int(day))
    except (ValueError, KeyError, AttributeError): return None


def source_iban(row):
    sequences = [('IBAN','BANCO','SUCURSAL','DC','CUENTA'), ('IBAN','BANCO','SUCURSAL','CUENTA1','CUENTA2','CUENTA3')]
    sizes = {'ES':24, 'IT':27, 'FR':27, 'DE':22, 'NL':18, 'BE':16, 'GB':22, 'PT':25}
    values = {''.join(row.get(k) or '' for k in seq).replace(' ', '').upper() for seq in sequences}
    valid = {v for v in values if is_valid_iban(v) and (v[:2] not in sizes or len(v)==sizes[v[:2]])}
    return valid.pop() if len(valid)==1 else None


def participants(unit):
    return {str(unit.get(k)) for k in ('CODINQUILINO1','CODINQUILINO2','CODINQUILINO3','CODPAGADOR') if unit.get(k) not in (None, '', '0')}


def category(unit, today):
    start, end = source_date(unit.get('FECHAINICIO')), source_date(unit.get('FECHAVENCIMIENTO'))
    if not start or not end or end < start: return 'Ambiguo'
    if unit.get('VACIO') not in ('S', 'N'): return 'Ambiguo'
    if start > today: return 'Futuro' if unit['VACIO']=='N' else 'Ambiguo'
    if end < today: return 'Vencido y vacío' if unit['VACIO']=='S' else 'Posible prórroga / requiere revisión'
    return 'Vigente pero vacío' if unit['VACIO']=='S' else 'Vigente confirmado'


def source_values(row, *, person_phone=True, phone_source=None):
    row = dict(row)
    row['address'] = ' '.join(row.get(k) or '' for k in ('DIR','DIRNUM','DIRPISO','DIRLETRA')).strip() or None
    row['iban'] = source_iban(row)
    if person_phone:
        row['TEL']=phone_candidates(row,phone_source)['value']
        row['address']=address_line(row)
    else:row['TEL']=phone_candidates(row,phone_source)['value']
    return {f: row.get(k) or None for f,k in PERSON_FIELDS.items() if person_phone or f!='country'}


def plausible(field, value):
    if not value or not isinstance(value, str) or any(ord(c)<32 for c in value): return False
    limits = {'email':254,'phone':40,'document_number':60,'address_line':255,'postal_code':20,'city':120,'province':120,'country':2,'iban':34}
    if len(value)>limits[field]: return False
    if field=='email': return bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value))
    if field=='phone': return phone_value(value) is not None
    if field=='iban': return is_valid_iban(value)
    if field=='country': return False
    return True


def public_value(field, value):
    return mask_iban(value) if field=='iban' else (value or '—')


@dataclass
class Action:
    source_id: str
    entity: str
    target_id: int | None
    operation: str
    field: str
    values: dict = field(default_factory=dict, repr=False)
    source_field: str | None = None
    source_original: str | None = field(default=None,repr=False)

    @property
    def key(self):
        return digest([self.source_id, self.entity, self.target_id, self.operation, self.field])


@dataclass
class Plan:
    id: str
    source_digest: str
    destination_digest: str
    actions: list[Action]
    skipped: list[str]

    @property
    def fingerprint(self):
        return digest([self.source_digest, self.destination_digest, [(a.key, a.values,a.source_field,a.source_original) for a in self.actions]])


class ReconciliationService:
    def load(self, db):
        # Fixed number of bulk SELECTs, no lazy relationships or N+1.
        return {model.__name__: list(db.scalars(select(model).order_by(model.id))) for model in
            (Person, Booking, BookingParty, Property, Room, Owner, OwnerBankAccount, PropertyOwnership, BookingFinancialTerms)}

    def destination_digest(self, db):
        data = self.load(db)
        return digest({name:[{c.key:getattr(obj,c.key) for c in inspect(type(obj)).column_attrs
            if c.key not in ('last_seen_in_feed_at', 'master_calendar_token')} for obj in rows] for name,rows in data.items()})

    def review(self, db, snapshot, property_mappings=None):
        data = self.load(db); tables=snapshot.tables; today=business_today(); property_mappings=property_mappings or {}
        units=tables.get('ALQ_INMUEBLES', []); people=list(tables.get('ALQ_INQUILINOS', []))
        current_ids={p['CODIGO'] for p in people}; needed={p for u in units for p in participants(u)}
        people += [dict(p, archived=True) for p in tables.get('ALQ_INQUILINOS_H', []) if p['CODIGO'] in needed-current_ids]
        fincas=[]; property_ids={p.id for p in data['Property']}
        for f in tables.get('ALQ_FINCAS', []):
            matches=[]
            for p in data['Property']:
                n=re.match(r'\d+',f.get('DIRNUM') or ''); pn=re.match(r'\d+',p.street_number or '')
                if n and pn and n.group()==pn.group() and max(similarity(f.get('DIR'),p.street),similarity(f.get('DIR'),p.name))>=.8:matches.append(p.id)
            chosen=property_mappings.get(f['CODIGO'])
            if chosen and chosen not in property_ids: raise ValueError('Finca destino inexistente.')
            fincas.append({'source':f,'candidates':matches,'chosen':chosen or (matches[0] if len(matches)==1 else None)})
        fmaps={f['source']['CODIGO']:f['chosen'] for f in fincas}
        room_maps={}
        for u in units:
            room_maps[u['CODIGO']]=[r.id for r in data['Room'] if r.property_id==fmaps.get(u['CODFINCA'])
                and re.search(r'\d+$',r.code) and (u.get('DIRLETRA') or '').isdigit()
                and int(re.search(r'\d+$',r.code).group())==int(u['DIRLETRA'])]
        links={b.id:{p.person_id for p in data['BookingParty'] if p.booking_id==b.id} for b in data['Booking']}
        person_rows=[]
        for src in people:
            associated=[u for u in units if src['CODIGO'] in participants(u)]
            rids={r for u in associated for r in room_maps[u['CODIGO']]}
            vals=source_values(src); telephone=phone_candidates(src); matches=[]
            for target in data['Person']:
                score=0; reasons=[]
                for f,w in [('document_number',55),('email',35),('phone',25),('iban',30)]:
                    if vals[f] and normalize(vals[f])==normalize(getattr(target,f)):
                        score+=w;reasons.append(f'{LABELS[f]} exacto')
                ns=similarity(src.get('APEYNOM'),target.full_name)
                if ns>=.9:score+=25;reasons.append('Nombre muy similar')
                elif ns>=.55:score+=10;reasons.append('Nombre parcialmente similar')
                matching=[b for b in data['Booking'] if b.room_id in rids and target.id in links[b.id]]
                if matching:
                    score+=25;reasons.append('Misma unidad candidata')
                    if any(b.check_in==source_date(u.get('FECHAINICIO')) for b in matching for u in associated):score+=15;reasons.append('Inicio exacto')
                    if any(b.check_out==source_date(u.get('FECHAVENCIMIENTO')) for b in matching for u in associated):score+=15;reasons.append('Fin exacto')
                if score>=25:matches.append({'target':target,'score':min(score,100),'reasons':reasons})
            matches.sort(key=lambda m:(-m['score'],m['target'].id))
            strong=bool(matches and matches[0]['score']>=65
                and any('Nombre' in r or 'Documento' in r for r in matches[0]['reasons'])
                and (len(matches)==1 or matches[0]['score']-matches[1]['score']>=15))
            state='Coincidencia fuerte' if strong else 'Ambiguo' if len(matches)>1 and matches[0]['score']-matches[1]['score']<15 else 'Probable' if matches else 'Nuevo'
            target=matches[0]['target'] if matches else None
            fields=[]
            for key,value in vals.items():
                old=getattr(target,key) if target else None
                status='Revisar teléfono' if key=='phone' and telephone['review'] else 'Falta en RentalManager' if not old else 'Coincide' if normalize(old)==normalize(value) else 'Diferente' if value else 'Sin dato de origen'
                fields.append({'key':key,'label':LABELS[key],'source':public_value(key,value),'target':public_value(key,old),'status':status,'available':plausible(key,value),'conflict':status=='Diferente'})
            person_rows.append({'source':{k:v for k,v in src.items() if k not in ('IBAN','BANCO','SUCURSAL','CUENTA','DC','CUENTA1','CUENTA2','CUENTA3')},
                'fields':fields,'phone':telephone,'matches':matches[:3],'state':state,'units':associated,'target':target,
                'eligible_new':any(category(u,today) in ('Vigente confirmado','Futuro') for u in associated)})
        contracts=[]
        for u in units:
            candidates=[]
            for b in data['Booking']:
                if b.room_id not in room_maps[u['CODIGO']]:continue
                reasons=['Unidad candidata'];score=25
                if b.check_in==source_date(u.get('FECHAINICIO')):score+=25;reasons.append('Inicio exacto')
                if b.check_out==source_date(u.get('FECHAVENCIMIENTO')):score+=25;reasons.append('Fin exacto')
                if any(p['target'] and p['target'].id in links[b.id] and p['state']=='Coincidencia fuerte' for p in person_rows if p['source']['CODIGO'] in participants(u)):
                    score+=25;reasons.append('Persona candidata fuerte')
                candidates.append({'target':b,'score':score,'reasons':reasons})
            candidates.sort(key=lambda c:(-c['score'],c['target'].id))
            cat=category(u,today)
            state='Fuera de alcance' if cat=='Vencido y vacío' else 'Ambiguo' if cat in ('Ambiguo','Vigente pero vacío','Posible prórroga / requiere revisión') else 'Candidato a nueva Booking' if not candidates else 'Existe pero faltan datos' if candidates[0]['score']==100 else 'Conflicto'
            if candidates and candidates[0]['score']==100 and any(t.booking_id==candidates[0]['target'].id for t in data['BookingFinancialTerms']):state='Existe y coincide'
            contracts.append({'source':u,'category':cat,'state':state,'rooms':room_maps[u['CODIGO']], 'matches':candidates,
                'start':source_date(u.get('FECHAINICIO')),'end':source_date(u.get('FECHAVENCIMIENTO')),
                'last_receipt':source_date(u.get('FECHA_ULT_RECIBO'))})
        owners=[]
        for src in tables.get('ALQ_PROPIETARIOS', []):
            matches=[]
            for o in data['Owner']:
                reasons=[]
                if src.get('NIF') and normalize(src['NIF'])==normalize(o.tax_id):reasons.append('Documento exacto')
                if source_iban(src) and any(b.owner_id==o.id and b.iban==source_iban(src) for b in data['OwnerBankAccount']):reasons.append('Cuenta exacta')
                if similarity(src.get('APEYNOM'),o.legal_name)>=.8:reasons.append('Nombre similar')
                if reasons:matches.append({'target':o,'reasons':reasons})
            owner_fields=[]
            for key,val in source_values(src,person_phone=False).items():
                if key=='iban':continue
                destkey='tax_id' if key=='document_number' else key
                old=getattr(matches[0]['target'],destkey) if matches else None
                owner_fields.append(dict(key=destkey,label=LABELS[key],source=('Disponible' if val else '—') if key=='document_number' else public_value(key,val),
                    target=('Disponible' if old else '—') if key=='document_number' else public_value(key,old),available=plausible(key,val)))
            owners.append({'id':src['CODIGO'],'name':src.get('APEYNOM'),'iban':mask_iban(source_iban(src)), 'matches':matches,'fields':owner_fields,'phone':phone_candidates(src),
                'relations':[r for r in tables.get('ALQ_INMUEBLES_INDIVISOS', []) if r['CODPROPIETARIO']==src['CODIGO']]})
        sepa=[]; pmap={p['CODIGO']:p for p in people}; bankmap={b['CODBANCO']:b.get('SWIFT') for b in tables.get('COMUN_BANCOS', [])}
        for u in units:
            payer=pmap.get(u.get('CODPAGADOR'),{}); f=next((f for f in tables.get('ALQ_FINCAS',[]) if f['CODIGO']==u['CODFINCA']),{})
            owner=next((o for o in tables.get('ALQ_PROPIETARIOS',[]) if o['CODIGO']==f.get('CODPROPIETARIO')), {})
            sepa.append({'unit':u['CODIGO'],'reference':u.get('REFDOMICI'),'date':source_date(u.get('FECHA_MANDATO')),
                'payer':payer.get('CODIGO'),'iban':mask_iban(source_iban(payer)), 'bic':bankmap.get(payer.get('BANCO')),
                'creditor':owner.get('CODIGO'),'creditor_account':mask_iban(source_iban(owner)),
                'warning':'Titular de cuenta no identificado' if not payer.get('TITULAR') else 'Verificar titular, firma, acreedor y referencia exacta',
                'eligible':False})
        return dict(people=person_rows,contracts=contracts,fincas=fincas,owners=owners,sepa=sepa,choices=data,
            counters={c:sum(x['category']==c for x in contracts) for c in ('Vigente confirmado','Posible prórroga / requiere revisión','Futuro','Vencido y vacío','Vigente pero vacío','Ambiguo')})

    def plan(self, db, snapshot, selections):
        if len(selections)>250:raise ValueError('Demasiadas selecciones en una ejecución.')
        actions=[]; skipped=[]; data=self.load(db); today=business_today(); tables=snapshot.tables
        reviewed={p['source']['CODIGO']:p for p in self.review(db,snapshot)['people']}
        people={p['CODIGO']:p for p in tables.get('ALQ_INQUILINOS_H',[])}
        people.update({p['CODIGO']:p for p in tables.get('ALQ_INQUILINOS',[])})
        units={u['CODIGO']:u for u in tables.get('ALQ_INMUEBLES',[])}
        owners={o['CODIGO']:o for o in tables.get('ALQ_PROPIETARIOS',[])}
        def target(model, ident):
            obj=db.get(model,int(ident))
            if obj is None:raise ValueError('Destino inexistente; revisar selección.')
            return obj
        for sel in selections:
            kind=sel.get('kind');sid=str(sel.get('source_id',''))
            if kind in ('person_fields','person_create'):
                src=people.get(sid)
                if not src:raise ValueError('Persona fuente inexistente.')
                vals=source_values(src,phone_source=sel.get('phone_source'))
                fields=sel.get('fields',[])
                if not isinstance(fields,list) or any(f not in PERSON_FIELDS for f in fields):raise ValueError('Campo no permitido; seleccione los campos de destino ofrecidos.')
                values={}
                for f in set(fields):
                    if not plausible(f,vals[f]):raise ValueError('Dato de origen incompleto o no válido.')
                    values[f]=vals[f].strip().lower() if f=='email' else vals[f].strip()
                if kind=='person_fields':
                    obj=target(Person,sel['target_id'])
                    candidate=reviewed.get(sid)
                    if 'iban' in values and not (candidate and candidate['state']=='Coincidencia fuerte'
                            and candidate['target'] and candidate['target'].id==obj.id):
                        raise ValueError('IBAN: confirmar una coincidencia fuerte con este inquilino.')
                    for f,v in values.items():
                        if getattr(obj,f) and str(getattr(obj,f)).strip():
                            skipped.append(f'Person {obj.id}.{f}: ya informado / conflicto; no sobrescribir.');continue
                        selected_phone=phone_candidates(src,sel.get('phone_source'))['chosen'] if f=='phone' else None
                        origin=('DIRSIGLA+DIR+DIRNUM+DIRPISO+DIRLETRA' if f=='address_line' else None)
                        original=(' | '.join(f'{k}={src.get(k) or ""}' for k in origin.split('+')) if origin else None)
                        actions.append(Action('person:'+sid,'Person',obj.id,'complete',f,{f:v},
                            source_field=selected_phone['field'] if selected_phone else origin,
                            source_original=selected_phone['original'] if selected_phone else original))
                else:
                    candidate=reviewed.get(sid)
                    if candidate and candidate['state']!='Nuevo' and not sel.get('identity_confirmed'):
                        raise ValueError('Identidad candidata o ambigua: confirmar expresamente el alta independiente.')
                    if not any(sid in participants(u) and category(u,today) in ('Vigente confirmado','Futuro') for u in units.values()):
                        raise ValueError('Alta fuera de un contrato vigente/futuro coherente; revisar primero.')
                    if not src.get('APEYNOM') or len(src['APEYNOM'])>160:raise ValueError('Nombre de origen no válido.')
                    if any(normalize(p.full_name)==normalize(src['APEYNOM']) or (vals['document_number'] and normalize(p.document_number)==normalize(vals['document_number'])) for p in data['Person']):
                        raise ValueError('Ya existe una identidad candidata. Revisar antes de crear.')
                    actions.append(Action('person:'+sid,'Person',None,'create','*',dict(full_name=src['APEYNOM'],source='manual',active=True,verification_status='unverified',**values)))
            elif kind in ('terms','booking_create','extension_review'):
                u=units.get(sid)
                if not u:raise ValueError('Unidad fuente inexistente.')
                cat=category(u,today)
                if kind=='extension_review':
                    skipped.append(f'Unidad {sid}: marcada para revisar prórroga SOLO en dry-run; no cambia fechas ni crea Booking.');continue
                if cat not in ('Vigente confirmado','Futuro'):raise ValueError('La vigencia necesita revisión; no crear ni modificar contratos automáticamente.')
                if not sel.get('context_confirmed'):raise ValueError('Confirmar manualmente unidad, identidad y contexto contractual.')
                if kind=='terms':
                    b=target(Booking,sel['target_id'])
                    if any(t.booking_id==b.id for t in data['BookingFinancialTerms']):raise ValueError('La Booking ya tiene condiciones; no sobrescribir.')
                    rent=self.money(u.get('RENTA'),positive=True)
                    deposit=self.money(u.get('FIANZA_IMPORTE') or '0') if sel.get('include_deposit') else Decimal('0')
                    due=int(sel.get('due_day',0))
                    if not 1<=due<=31:raise ValueError('Seleccionar vencimiento entre 1 y 31.')
                    actions.append(Action('unit:'+sid,'BookingFinancialTerms',None,'create','*',dict(booking_id=b.id,version=1,effective_from=b.check_in,monthly_rent=rent,deposit_agreed=deposit,usual_due_day=due,currency='EUR',status='draft')))
                else:
                    room=target(Room,sel['room_id']);person=target(Person,sel['person_id'])
                    if not room.active:raise ValueError('La habitación está archivada.')
                    start,end=source_date(u.get('FECHAINICIO')),source_date(u.get('FECHAVENCIMIENTO'))
                    if not start or not end or end<=start:raise ValueError('Periodo inválido.')
                    if not sel.get('half_open_confirmed'):raise ValueError('Confirmar fin contractual exclusivo; no se transforma la fecha automáticamente.')
                    if any(b.room_id==room.id and b.check_in<end and b.check_out>start for b in data['Booking']):raise ValueError('Existe una reserva solapada; revisar, no duplicar.')
                    actions.append(Action('unit:'+sid,'Booking',None,'create','*',dict(room_id=room.id,check_in=start,check_out=end,origin='manual',_person_id=person.id)))
            elif kind in ('owner_create','owner_account','owner_fields'):
                src=owners.get(sid)
                if not src:raise ValueError('Propietario fuente inexistente.')
                if kind=='owner_fields':
                    owner=target(Owner,sel['target_id'])
                    fieldmap={'email':'MAIL','phone':'TEL','tax_id':'NIF','address_line':'DIR','postal_code':'CP','city':'POB','province':'PROVINCIA'}
                    selected=sel.get('fields',[])
                    if not isinstance(selected,list) or any(f not in fieldmap for f in selected):raise ValueError('Campo de propietario no permitido.')
                    for f in set(selected):
                        val=src.get(fieldmap[f])
                        telephone=phone_candidates(src,sel.get('phone_source')) if f=='phone' else None
                        if telephone:val=telephone['value']
                        if f=='address_line':val=' '.join(src.get(k) or '' for k in ('DIR','DIRNUM')).strip()
                        if not plausible('document_number' if f=='tax_id' else f,val) or (f=='tax_id' and len(val)>40):raise ValueError('Dato de propietario no válido.')
                        if getattr(owner,f):skipped.append(f'Propietario {owner.id}: {f} ya informado; no sobrescribir.');continue
                        actions.append(Action('owner:'+sid,'Owner',owner.id,'complete',f,{f:val.strip()},
                            source_field=telephone['chosen']['field'] if telephone else None,
                            source_original=telephone['chosen']['original'] if telephone else None))
                elif kind=='owner_create':
                    if any(normalize(o.legal_name)==normalize(src.get('APEYNOM')) or (src.get('NIF') and normalize(o.tax_id)==normalize(src['NIF'])) for o in data['Owner']):raise ValueError('Propietario posiblemente existente; revisar antes de crear.')
                    if not src.get('APEYNOM') or len(src['APEYNOM'])>180:raise ValueError('Nombre de propietario no válido.')
                    actions.append(Action('owner:'+sid,'Owner',None,'create','*',dict(legal_name=src['APEYNOM'],tax_id=src.get('NIF'),active=True)))
                else:
                    owner=target(Owner,sel['target_id']);iban=source_iban(src);holder=str(sel.get('holder','')).strip()
                    if not iban or not holder or len(holder)>180 or not sel.get('holder_confirmed'):raise ValueError('Cuenta o titular sin verificar.')
                    if any(b.owner_id==owner.id and b.iban==iban for b in data['OwnerBankAccount']):raise ValueError('Cuenta ya existente.')
                    actions.append(Action('owner:'+sid,'OwnerBankAccount',None,'create','*',dict(owner_id=owner.id,iban=iban,account_holder_name=holder,active=True,receives_rent=False,receives_settlements=False,currency='EUR')))
            else:raise ValueError('Operación no permitida. SEPA permanece como candidato sin alta automática.')
        # Same source creation cannot produce two identities in one plan.
        if len({a.key for a in actions})!=len(actions):raise ValueError('Selección duplicada.')
        return Plan(str(uuid.uuid4()), snapshot.fingerprint, self.destination_digest(db), actions, skipped)

    @staticmethod
    def money(value,positive=False):
        try:
            amount=Decimal(str(value))
            if not amount.is_finite() or amount<0 or (positive and amount==0) or amount>Decimal('9999999999.99') or amount!=amount.quantize(Decimal('.01')):raise ValueError()
            return amount
        except (InvalidOperation,ValueError):raise ValueError('Importe contractual no válido; no inferirlo de recibos.') from None

    def apply(self, db, snapshot, plan):
        # Reject even plans prepared before PAIS was declared unreliable.
        if any(a.field=='country' or 'country' in a.values for a in plan.actions):
            raise ValueError('País NetFincas no importable. Repita la revisión sin ese campo.')
        with financial_transaction(db):
            existing=db.get(MigrationRun,plan.id)
            if existing:
                if existing.plan_digest!=plan.fingerprint:raise ValueError('Identificador de plan inconsistente.')
                return existing.id
            if snapshot.fingerprint!=plan.source_digest or self.destination_digest(db)!=plan.destination_digest:
                raise ValueError('Origen o destino ha cambiado. Repetir dry-run.')
            if not plan.actions:raise ValueError('No hay acciones aplicables seleccionadas.')
            if any(db.scalar(select(MigrationAction.id).where(MigrationAction.action_key==a.key)) for a in plan.actions):
                raise ValueError('Hay acciones ya aplicadas. Revisar trazabilidad y repetir dry-run.')
            run=MigrationRun(id=plan.id,source='NetFincas',source_digest=plan.source_digest,plan_digest=plan.fingerprint,result='applied')
            db.add(run);db.flush()
            for a in plan.actions:
                model=MODELS[a.entity];values=dict(a.values);person_id=values.pop('_person_id',None)
                if a.operation=='complete':
                    obj=db.get(model,a.target_id)
                    if obj is None or (getattr(obj,a.field) and str(getattr(obj,a.field)).strip()):raise ValueError('Campo ya informado; operación cancelada íntegramente.')
                    setattr(obj,a.field,values[a.field])
                else:
                    if a.entity=='Booking' and db.scalar(select(Booking.id).where(Booking.room_id==values['room_id'],Booking.check_in<values['check_out'],Booking.check_out>values['check_in'])):
                        raise ValueError('Réservas solapadas en la selección; cancelar íntegramente.')
                    if a.entity=='Person':
                        for other in db.scalars(select(Person)):
                            if normalize(other.full_name)==normalize(values['full_name']) or (values.get('document_number') and normalize(other.document_number)==normalize(values['document_number'])):
                                raise ValueError('Identidad duplicada dentro de la selección.')
                    obj=model(**values);db.add(obj)
                db.flush()
                if person_id is not None:
                    party=BookingParty(booking_id=obj.id,person_id=person_id,role='unclassified')
                    db.add(party);db.flush()
                    db.add(MigrationAction(run_id=run.id,action_key=digest([a.key,'unclassified']),source_id=a.source_id,
                        entity='BookingParty',target_id=party.id,operation='create',field='role',result='applied'))
                db.add(MigrationAction(run_id=run.id,action_key=a.key,source_id=a.source_id+(':'+a.source_field if a.source_field else ''),entity=a.entity,
                    target_id=obj.id,operation=a.operation,field=a.field,result='applied'))
            return run.id
