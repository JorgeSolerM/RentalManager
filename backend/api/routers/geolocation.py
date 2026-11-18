"""Local administrative review; never registered on the public application."""
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import hmac
import ipaddress
import os
import secrets
import sqlite3
import time
from urllib.parse import urlencode, urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.models.property import Property
from backend.public.map_locations import Address, LocationCache, geocoder_url
from backend.services.geocoding_queries import diagnostics
from backend.services.geolocation_incident_service import REASONS

router = APIRouter(prefix='/properties')
templates = Jinja2Templates(directory='backend/templates')
_secret = secrets.token_bytes(32)
MESSAGES = {
    'verified': 'Ubicación verificada. La incidencia desaparece de las abiertas y el mapa utilizará la ubicación al recargar.',
    'review': 'No se ha podido verificar la ubicación. Revisa el diagnóstico de las variantes.',
    'error': 'El proveedor no respondió correctamente. Se ha establecido una pausa de 24 horas.',
    'paused': 'El proveedor está en pausa. No se ha realizado ninguna consulta.',
    'exhausted': 'Se ha alcanzado el máximo de tres intentos de una variante. Revisa la dirección; no se elude el límite.',
    'cached': 'Se conservan los resultados anteriores. No se repiten variantes antes de 24 horas ni tras tres intentos.',
    'incomplete': 'Completa calle, número y ciudad antes de consultar.',
    'disabled': 'Los reintentos administrativos no están habilitados. Su activación requiere configurar el escritor autorizado de la caché.',
    'unavailable': 'La caché no permite esta operación o está ocupada. No se han cambiado permisos; revisa su configuración.',
    'configuration': 'Falta la identificación de la aplicación o la configuración HTTPS del proveedor.',
    'saved': 'Dirección guardada. La ubicación anterior deja de aplicarse si cambió la dirección; puedes reintentar.',
    'invalid': 'Completa los campos obligatorios del formulario.',
}


def local_admin(request):
    try:
        valid = ipaddress.ip_address(request.client.host).is_loopback
    except (ValueError, AttributeError):
        valid = False
    if not valid or request.url.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise HTTPException(403, 'Disponible únicamente desde la administración local.')


def property_for(db, property_id):
    obj = db.get(Property, property_id)
    if obj is None: raise HTTPException(404, 'Finca no encontrada.')
    return obj


def signed(session, property_id, key, expires):
    return hmac.new(_secret, f'{session}|{property_id}|{key}|{expires}'.encode(), hashlib.sha256).hexdigest()


def protect(request, obj, form):
    local_admin(request)
    session = request.cookies.get('geo_review', '')
    key = Address.of(obj).key
    try:
        expires, signature = str(form.get('csrf','')).split(':',1)
        if not session or not time.time() < int(expires) <= time.time()+1801:
            raise ValueError()
        if not hmac.compare_digest(signed(session,obj.id,key,expires), signature): raise ValueError()
    except ValueError:
        raise HTTPException(403, 'Formulario caducado o dirección modificada. Recarga la revisión.')
    origin = request.headers.get('origin')
    opaque = origin == 'null' and request.headers.get('sec-fetch-site') == 'same-origin'
    if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and origin != str(request.base_url).rstrip('/') and not opaque):
        raise HTTPException(403, 'Origen de formulario no permitido.')


def when(value):
    return datetime.fromtimestamp(value, ZoneInfo('Europe/Madrid')).strftime('%d/%m/%Y %H:%M') if value else 'Sin consulta registrada'


@router.get('/{property_id}/geolocation')
def review(request: Request, property_id: int, db: Session = Depends(get_db)):
    local_admin(request)
    obj = property_for(db, property_id); address = Address.of(obj)
    try:
        detail = diagnostics(LocationCache(), address)
    except (sqlite3.Error, OSError):
        detail = {'entry':None,'attempts':[],'next_request':0}
    entry = detail['entry'] or {}
    session = request.cookies.get('geo_review') or secrets.token_urlsafe(32)
    expires = str(int(time.time())+1800)
    token = expires+':'+signed(session,obj.id,address.key,expires)
    registered = f'{address.street} {address.number}, {address.city}'
    reason = entry.get('reason','not_attempted')
    explanation = REASONS.get(reason, 'No hay una consulta registrada para la dirección actual.')
    if reason.startswith('http_') and reason[5:].isdigit(): explanation = 'Respuesta del proveedor: HTTP '+reason[5:]
    response = templates.TemplateResponse(request=request,name='pages/property_geolocation.html',context={
        'request':request,'current_page':'properties','property':obj,'registered':registered,
        'manual_location_update_enabled': True,
        'status':{'verified':'Verificada','review':'Requiere revisión','error':'Error del proveedor'}.get(entry.get('status'),'Pendiente'),
        'reason':explanation,'attempted':when(entry.get('checked_at')),'attempts':detail['attempts'],
        'when':when,'csrf':token,'notice':MESSAGES.get(request.query_params.get('result',''),''),
        'pause_until':when(detail['next_request']) if detail['next_request']>time.time() else None,
        'retry_enabled':os.getenv('PUBLIC_GEOCODING_ADMIN_RETRY_ENABLED')=='1',
        'maps_url':'https://www.google.com/maps/search/?'+urlencode({'api':1,'query':registered}),
    })
    response.set_cookie('geo_review',session,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=1800)
    response.headers['Cache-Control']='no-store'
    response.headers['Referrer-Policy']='no-referrer'
    return response


def redirect(property_id, result):
    return RedirectResponse(f'/properties/{property_id}/geolocation?'+urlencode({'result':result}),status_code=303)


def retry_address(address):
    if os.getenv('PUBLIC_GEOCODING_ADMIN_RETRY_ENABLED')!='1': return 'disabled'
    agent=os.getenv('PUBLIC_GEOCODER_USER_AGENT','').strip()
    if not agent or urlsplit(geocoder_url()).scheme!='https': return 'configuration'
    try:
        with httpx.Client(headers={'User-Agent':agent},timeout=15,follow_redirects=False) as client:
            return LocationCache().resolve_progressive(address,client=client,manual=True)
    except (sqlite3.Error, OSError):
        return 'unavailable'
    except ValueError:
        return 'configuration'


@router.post('/{property_id}/geolocation/retry')
async def retry(request: Request, property_id: int, db: Session = Depends(get_db)):
    obj=property_for(db,property_id);form=await request.form();protect(request,obj,form)
    address=Address.of(obj)
    if not obj.active or not obj.is_published: return redirect(property_id,'disabled')
    db.rollback()  # Release the business read transaction before any network wait.
    result=await run_in_threadpool(retry_address,address)
    return redirect(property_id,result)


@router.post('/{property_id}/geolocation/address')
async def save_address(request: Request, property_id: int, db: Session = Depends(get_db)):
    obj=property_for(db,property_id);form=await request.form();protect(request,obj,form)
    if not all(str(form.get(k,'')).strip() for k in ('name','street','city')):
        return redirect(property_id,'invalid')
    from backend.api.routers.properties import update_property
    # Reuse the existing controller/service, including validation and legacy fields.
    result=update_property(property_id=property_id,db=db,**{k:str(form.get(k,'')) for k in
        ('name','alias','street','street_number','floor','door','city','notes')})
    return redirect(property_id,'saved' if 'success=' in result.headers['location'] else 'invalid')
