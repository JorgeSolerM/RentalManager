"""Opt-in internal admin workflow; private plans never travel to the browser."""
import os
from pathlib import Path
import secrets
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from backend.database.session import get_db
from backend.models.migration_audit import MigrationRun, MigrationAction
from backend.services.netfincas_source import FirebirdSource, SourceUnavailable
from backend.services.netfincas_reconciliation import ReconciliationService, public_value, source_values, plausible, normalize, LABELS, MODELS, participants
from backend.models import Person, Booking, Room, Property
from backend.services.netfincas_phone import phone_candidates

router=APIRouter(prefix='/reconciliation/netfincas')
templates=Jinja2Templates(directory='backend/templates')
service=ReconciliationService()


class ReviewStore:
    """Process-local expiring private snapshots; restart requires fresh dry-run."""
    def __init__(self):self.entries={};self.lock=threading.Lock()
    def put(self,session,value):
        with self.lock:
            self.entries={k:v for k,v in self.entries.items() if time.monotonic()-v[0]<900}
            if len(self.entries)>=32:raise ValueError('Demasiadas revisiones abiertas; cierre o espere a que caduquen.')
            token=secrets.token_urlsafe(32);self.entries[token]=(time.monotonic(),session,value);return token
    def get(self,token,session):
        with self.lock:
            entry=self.entries.get(token)
            if not entry or time.monotonic()-entry[0]>900 or not secrets.compare_digest(entry[1],session):
                raise ValueError('La revisión ha caducado. Volver a cargar y repetir dry-run.')
            return entry[2]


def setup(app):
    app.state.netfincas_enabled=os.getenv('NETFINCAS_RECONCILIATION_ENABLED')=='1'
    app.state.netfincas_apply_database=os.getenv('NETFINCAS_APPLY_DATABASE','')
    app.state.netfincas_store=ReviewStore()
    app.state.netfincas_source=FirebirdSource(
        Path(os.getenv('NETFINCAS_SOURCE_DATABASE','data/runtime/netfincas_audit/audit_work.ib')),
        Path(os.getenv('NETFINCAS_ISQL','data/runtime/netfincas_audit/embedded207/isql.exe')))


def enabled(request):
    if not request.app.state.netfincas_enabled:raise HTTPException(404)


def apply_allowed(request,db):
    expected=request.app.state.netfincas_apply_database
    actual=db.get_bind().url.database
    return bool(expected and actual and Path(expected).resolve()==Path(actual).resolve())


def render(request,**context):
    response=templates.TemplateResponse(request=request,name='pages/netfincas.html',context=dict(request=request,**context))
    response.headers['Cache-Control']='no-store'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['X-Robots-Tag']='noindex, nofollow'
    return response


def comparison(source,target,strong=False,phone_source=None):
    fields=[]
    telephone=phone_candidates(source,phone_source)
    for key,value in source_values(source,phone_source=phone_source).items():
        old=getattr(target,key) if target else None
        status='Falta en RentalManager' if not old else 'Coincide' if value and normalize(old)==normalize(value) else 'Diferente' if value else 'Sin dato de origen'
        if key=='phone' and telephone['review']:status='Revisar teléfono'
        fields.append(dict(key=key,label=LABELS[key],source=('Disponible' if value else '—') if key=='document_number' else public_value(key,value),
            target=('Disponible' if old else '—') if key=='document_number' else public_value(key,old),status=status,
            selectable=bool(target and not old and plausible(key,value) and (key!='iban' or strong))))
    return fields


def decorate(review):
    props={p.id:p for p in review['choices']['Property']}
    rooms={r.id:r for r in review['choices']['Room']}
    fincas={f['source']['CODIGO']:f['source'] for f in review['fincas']}
    people={p['source']['CODIGO']:p for p in review['people']}
    for c in review['contracts']:
        f=fincas.get(c['source']['CODFINCA'],{})
        c['title']=' '.join(f.get(k) or '' for k in ('DIR','DIRNUM'))+' · '+(' / '.join(c['source'].get(k) or '' for k in ('DIRPISO','DIRLETRA')))
        c['names']=' / '.join(people[s]['source'].get('APEYNOM','') for s in participants(c['source']) if s in people)
    for p in review['people']:
        active=any(c['source']['CODIGO'] in {u['CODIGO'] for u in p['units']} and c['category']=='Vigente confirmado' for c in review['contracts'])
        p['completable']=active and p['state']=='Coincidencia fuerte' and any(f['available'] and f['status']=='Falta en RentalManager' for f in p['fields'])
        for f in p['fields']:
            f['selectable']=bool(f['available'] and f['status']=='Falta en RentalManager' and p['target'] and (f['key']!='iban' or p['state']=='Coincidencia fuerte'))
            if f['key']=='document_number':
                f['source']='Disponible' if f['source']!='—' else '—'
                f['target']='Disponible' if f['target']!='—' else '—'
        p['places']=[c['title'] for c in review['contracts'] if c['source']['CODIGO'] in {u['CODIGO'] for u in p['units']}]
    review['people'].sort(key=lambda p:(not p['completable'],p['state']!='Coincidencia fuerte',p['source'].get('APEYNOM','')))
    review['booking_labels']={b.id:f"{props[rooms[b.room_id].property_id].name} · {rooms[b.room_id].code} · {b.check_in:%d/%m/%Y} → {b.check_out:%d/%m/%Y}" for b in review['choices']['Booking']}
    review['room_labels']={r.id:f'{props[r.property_id].name} · {r.code}' for r in rooms.values()}
    return review


def csrf(request,form):
    cookie=request.cookies.get('nf_review','')
    supplied=str(form.get('csrf',''))
    if not cookie or not secrets.compare_digest(cookie,supplied):raise HTTPException(403,'Formulario no válido; recargue la revisión.')
    origin=request.headers.get('origin')
    # The admin layout uses no-referrer: Chromium can send Origin: null for
    # same-origin forms. Require Fetch Metadata AND the session-bound token.
    local_opaque_origin = origin == 'null' and request.headers.get('sec-fetch-site') == 'same-origin'
    if origin and origin!=str(request.base_url).rstrip('/') and not local_opaque_origin:
        raise HTTPException(403,'Origen no permitido.')
    return cookie


@router.get('')
def index(request:Request,db=Depends(get_db)):
    enabled(request);session=request.cookies.get('nf_review') or secrets.token_urlsafe(32)
    try:
        snapshot=request.app.state.netfincas_source.read()
        review=decorate(service.review(db,snapshot))
        token=request.app.state.netfincas_store.put(session,snapshot)
        response=render(request,mode='review',review=review,token=token,csrf=session)
    except (SourceUnavailable,ValueError) as exc:
        response=render(request,mode='error',error=str(exc))
    response.set_cookie('nf_review',session,httponly=True,samesite='strict',secure=request.url.scheme=='https',path='/reconciliation/netfincas',max_age=900)
    return response


def selections(form):
    result=[]
    for sid in form.getlist('person_select'):
        dest=form.get('person_target_'+sid)
        result.append(dict(kind='person_create' if dest=='new' else 'person_fields',source_id=sid,target_id=dest,
            fields=form.getlist('person_fields_'+sid),phone_source=form.get('phone_source_'+sid),identity_confirmed=bool(form.get('identity_'+sid))))
    for sid in form.getlist('unit_select'):
        kind=form.get('unit_action_'+sid)
        result.append(dict(kind=kind,source_id=sid,target_id=form.get('booking_'+sid),room_id=form.get('room_'+sid),person_id=form.get('person_'+sid),
            due_day=form.get('due_'+sid),include_deposit=bool(form.get('deposit_'+sid)),context_confirmed=bool(form.get('context_'+sid)),half_open_confirmed=bool(form.get('end_'+sid))))
    for sid in form.getlist('owner_select'):
        result.append(dict(kind=form.get('owner_action_'+sid),source_id=sid,target_id=form.get('owner_target_'+sid),phone_source=form.get('owner_phone_source_'+sid),holder=form.get('holder_'+sid),holder_confirmed=bool(form.get('holder_confirmed_'+sid)),fields=form.getlist('owner_fields_'+sid)))
    return result


@router.post('/dry-run')
async def dry_run(request:Request,db=Depends(get_db)):
    enabled(request);form=await request.form();session=csrf(request,form)
    try:
        snapshot=request.app.state.netfincas_store.get(str(form.get('token','')),session)
        plan=service.plan(db,snapshot,selections(form))
        token=request.app.state.netfincas_store.put(session,plan)
        rows=[]
        for a in plan.actions:
            obj=db.get(MODELS[a.entity],a.target_id) if a.target_id else None
            name=getattr(obj,'full_name',None) or getattr(obj,'legal_name',None) or a.values.get('full_name') or a.values.get('legal_name')
            values={LABELS.get(k,{'_person_id':'Inquilino inicial (sin clasificar)','monthly_rent':'Renta mensual','deposit_agreed':'Fianza','check_in':'Inicio de contrato','check_out':'Fin de contrato'}.get(k,k)):('Disponible (no se muestra el documento)' if k in ('document_number','tax_id') else public_value(k,str(v) if v is not None else None)) for k,v in a.values.items()}
            if a.source_field:
                values['Campo de origen NetFincas']=a.source_field
                values['Valor original NetFincas']=a.source_original
            if a.entity=='Booking':
                r=db.get(Room,a.values['room_id']);p=db.get(Person,a.values['_person_id'])
                name=f'{db.get(Property,r.property_id).name} · {r.code} · {p.full_name}'
                source_unit=next((u for u in snapshot.tables.get('ALQ_INMUEBLES',[]) if 'unit:'+u['CODIGO']==a.source_id),{})
                values['Renta candidata']=(source_unit.get('RENTA') or 'No informada')+' · no se importa con el alta; requiere condiciones en draft por separado.'
            if a.entity=='BookingFinancialTerms':
                b=db.get(Booking,a.values['booking_id']);r=db.get(Room,b.room_id)
                name=f'{db.get(Property,r.property_id).name} · {r.code}'
            rows.append(dict(source=a.source_id,entity=a.entity,target=a.target_id,name=name,operation=a.operation,field=LABELS.get(a.field,a.field),values=values))
        summary=dict(fields=sum(a.operation=='complete' for a in plan.actions),people=len({a.target_id for a in plan.actions if a.entity=='Person' and a.target_id}),bookings=sum(a.entity=='Booking' for a in plan.actions))
        return render(request,mode='plan',plan_rows=rows,summary=summary,skipped=plan.skipped,token=token,csrf=session,can_apply=apply_allowed(request,db))
    except (ValueError,TypeError,KeyError):
        # No submitted data or bank values in validation responses/logs.
        return render(request,mode='error',error='Selección no aplicable: revise identidad/contexto, campos vacíos, importes y fechas. No se ha escrito nada.')


@router.post('/compare')
async def compare_person(request:Request,db=Depends(get_db)):
    enabled(request);form=await request.form();session=csrf(request,form)
    try:
        snapshot=request.app.state.netfincas_store.get(str(form.get('token','')),session)
        sid=str(form.get('source_id',''));dest=str(form.get('target_id',''))
        rows={p['CODIGO']:p for p in snapshot.tables.get('ALQ_INQUILINOS_H',[])}
        rows.update({p['CODIGO']:p for p in snapshot.tables.get('ALQ_INQUILINOS',[])})
        candidate=next(p for p in service.review(db,snapshot)['people'] if p['source']['CODIGO']==sid)
        target=None if dest=='new' else db.get(Person,int(dest))
        strong=bool(target and candidate['state']=='Coincidencia fuerte' and candidate['target'].id==target.id)
        phone_source=form.get('phone_source') or None
        result=comparison(rows[sid],target,strong,phone_source)
        if dest=='new':
            for f in result:f['selectable']=plausible(f['key'],source_values(rows[sid],phone_source=phone_source)[f['key']]) and f['key']!='iban'
        from fastapi.responses import JSONResponse
        return JSONResponse({'fields':result},headers={'Cache-Control':'no-store'})
    except (ValueError,KeyError,StopIteration,TypeError):
        raise HTTPException(400,'No se pudo comparar el destino. Recargue la revisión.') from None


@router.post('/apply')
async def apply_selected(request:Request,db=Depends(get_db)):
    enabled(request);form=await request.form();session=csrf(request,form)
    if not apply_allowed(request,db):raise HTTPException(403,'Aplicación deshabilitada para esta base de datos.')
    if form.get('confirm')!='yes':raise HTTPException(400,'Confirmación explícita necesaria.')
    try:
        plan=request.app.state.netfincas_store.get(str(form.get('token','')),session)
        snapshot=request.app.state.netfincas_source.read()
        run_id=service.apply(db,snapshot,plan)
        return render(request,mode='success',run_id=run_id)
    except (ValueError,IntegrityError,SourceUnavailable):
        db.rollback()
        return render(request,mode='error',error='Aplicación cancelada íntegramente: revisión caducada, conflicto o dato no válido. Repita el dry-run; no se han realizado cambios parciales.')


@router.get('/runs')
def runs(request:Request,db=Depends(get_db)):
    enabled(request)
    return render(request,mode='runs',runs=list(db.scalars(select(MigrationRun).order_by(MigrationRun.created_at.desc()).limit(100))),
        actions=list(db.scalars(select(MigrationAction).order_by(MigrationAction.id.desc()).limit(500))))
