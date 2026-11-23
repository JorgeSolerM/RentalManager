import asyncio
import json
import re
import time
from datetime import date

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.core.admin_access import AccessConfig, AccessDenied, AccessVerifier
from backend.core.admin_security import AdminSecurityMiddleware


@pytest.fixture(scope='module')
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def config():
    return AccessConfig(True, 'admin.example.test', 'https://test-team.cloudflareaccess.com', 'aud-test', ('owner@example.test',))


def signed(key, **changes):
    claims = dict(iss='https://test-team.cloudflareaccess.com', aud='aud-test',
                  sub='synthetic-operator', email='owner@example.test',
                  iat=int(time.time()), exp=int(time.time()) + 300, type='app')
    claims.update(changes)
    return jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'test-key'})


def verifier(config, key):
    async def fetch():
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        return {'keys': [{**jwk, 'kid': 'test-key', 'alg': 'RS256', 'use': 'sig'}]}
    return AccessVerifier(config, fetch=fetch)


def headers(key):
    return {'X-Forwarded-Proto': 'https', 'Cf-Access-Jwt-Assertion': signed(key)}


def csrf(client):
    response = client.get('/')
    assert response.status_code == 200, response.text
    return re.search(r'name="rm-admin-csrf" content="([^"]+)"', response.text)[1]


def app_for(config, key, sink=None):
    app = FastAPI()
    app.state.writes = 0
    @app.get('/')
    def index(request: Request):
        return HTMLResponse(f'<meta name="rm-admin-csrf" content="{request.state.admin_csrf}">')
    @app.post('/bookings/person-search')
    async def search(request: Request):
        return {'query': (await request.form()).get('query'), 'identity': request.state.admin_identity}
    @app.post('/write')
    async def write(request: Request):
        app.state.writes += 1
        return {'ok': True, 'form': dict(await request.form()), 'identity': request.state.admin_identity}
    @app.get('/ical/rooms/token/platform.ics')
    def ical():
        return HTMLResponse('BEGIN:VCALENDAR\r\nEND:VCALENDAR', media_type='text/calendar')
    app.add_middleware(AdminSecurityMiddleware, config=config, verifier=verifier(config, key), sink=sink)
    return app


def client_for(app, remote=False, key=None, peer='127.0.0.1'):
    return TestClient(app, base_url='https://admin.example.test' if remote else 'http://127.0.0.1',
                      client=(peer, 1234), headers=headers(key) if remote else {})


def test_local_csrf_form_and_header_keep_local_identity(config, key):
    app = app_for(config, key)
    with client_for(app) as c:
        token = csrf(c)
        assert c.post('/write', data={'value': 'keep'}).status_code == 403
        response = c.post('/write', data={'value': 'keep', '_rm_csrf': token})
        assert response.status_code == 200 and response.json()['form']['value'] == 'keep'
        assert response.json()['identity'] is None
        assert c.post('/write', headers={'X-RM-CSRF': token}).status_code == 200
        assert app.state.writes == 2


def test_remote_signed_identity_and_post_search(config, key):
    app = app_for(config, key)
    with client_for(app, True, key) as c:
        token = csrf(c)
        response = c.post('/bookings/person-search', data={'query': 'synthetic', '_rm_csrf': token})
        assert response.status_code == 200
        assert response.json()['identity']['source'] == 'cloudflare_access'
        assert response.json()['query'] == 'synthetic'
        assert c.post('/write', headers={'X-RM-CSRF': token}).status_code == 403
        assert app.state.writes == 0


@pytest.mark.parametrize('change', [
    {'exp': 1}, {'aud': 'wrong'}, {'iss': 'https://other.cloudflareaccess.com'},
    {'email': 'other@example.test'}, {'iat': int(time.time()) + 3600},
    {'nbf': int(time.time()) + 3600}, {'type': 'service'},
])
def test_invalid_claims(config, key, change):
    with client_for(app_for(config, key), True, key) as c:
        assert c.get('/', headers={'Cf-Access-Jwt-Assertion': signed(key, **change)}).status_code == 401


@pytest.mark.parametrize('claim', ['exp', 'iat', 'sub', 'email', 'iss', 'aud'])
def test_missing_claim(config, key, claim):
    payload = jwt.decode(signed(key), options={'verify_signature': False})
    del payload[claim]
    token = jwt.encode(payload, key, algorithm='RS256', headers={'kid':'test-key'})
    with client_for(app_for(config,key),True,key) as c:
        assert c.get('/',headers={'Cf-Access-Jwt-Assertion':token}).status_code==401


@pytest.mark.parametrize('token', ['', 'nonsense', 'a.b.c'])
def test_missing_malformed(config, key, token):
    with client_for(app_for(config,key),True,key) as c:
        assert c.get('/',headers={'Cf-Access-Jwt-Assertion':token}).status_code==401


def test_signature_algorithm_and_duplicate_header(config, key):
    app=app_for(config,key)
    other=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    with client_for(app,True,key) as c:
        assert c.get('/',headers={'Cf-Access-Jwt-Assertion':signed(other)}).status_code==401
        payload=jwt.decode(signed(key),options={'verify_signature':False})
        for algorithm, signing_key in [('none',None),('HS256','synthetic-key-only-for-test-1234567890')]:
            token=jwt.encode(payload,signing_key,algorithm=algorithm,headers={'kid':'test-key'})
            assert c.get('/',headers={'Cf-Access-Jwt-Assertion':token}).status_code==401
        assert c.get('/',headers=[('Cf-Access-Jwt-Assertion',signed(key)),('Cf-Access-Jwt-Assertion',signed(key))]).status_code==401


@pytest.mark.parametrize('path', ['/docs','/openapi.json','/redoc','/_ops/ready','/_ops/live',
    '/settings','/expenses/new','/persons/new','/rooms/edit/1','/unknown','/ical/rooms/token/platform.ics'])
def test_remote_routes_fail_closed(config,key,path):
    with client_for(app_for(config,key),True,key) as c:
        assert c.get(path).status_code==403


@pytest.mark.parametrize('method', ['POST','PUT','PATCH','DELETE','OPTIONS'])
def test_remote_mutation_methods(config,key,method):
    with client_for(app_for(config,key),True,key) as c:
        assert c.request(method,'/expenses/1').status_code==403


@pytest.mark.parametrize('extra', [
    {'Cf-Access-Jwt-Assertion':'forged'}, {'Cf-Access-Authenticated-User-Email':'owner@example.test'},
    {'X-Forwarded-For':'127.0.0.1'}, {'X-Forwarded-Host':'admin.example.test'},
    {'X-Forwarded-Proto':'https'}, {'Forwarded':'for=127.0.0.1'}, {'Cf-Connecting-Ip':'127.0.0.1'}])
def test_local_proxy_spoof_rejected(config,key,extra):
    with client_for(app_for(config,key)) as c:
        assert c.get('/',headers=extra).status_code==403


@pytest.mark.parametrize('host', ['evil.test','127.0.0.1.evil.test','localhost@evil.test','localhost/evil'])
def test_host_restriction(config,key,host):
    with client_for(app_for(config,key)) as c:
        assert c.get('/',headers={'Host':host}).status_code in {400,403}


def test_remote_nonloopback_and_disabled(config,key):
    with client_for(app_for(config,key),True,key,peer='203.0.113.2') as c:
        assert c.get('/').status_code==403
    with client_for(app_for(AccessConfig(),key),True,key) as c:
        assert c.get('/').status_code==403
    with client_for(app_for(config,key),peer='203.0.113.2') as c:
        assert c.get('/').status_code==403


@pytest.mark.parametrize('extra', [{'Origin':'https://evil.test'},{'Origin':'null'},
    {'Sec-Fetch-Site':'cross-site'},{'Sec-Fetch-Site':'same-site'}])
def test_csrf_cross_origin_even_with_token(config,key,extra):
    with client_for(app_for(config,key)) as c:
        token=csrf(c)
        assert c.post('/write',headers={**extra,'X-RM-CSRF':token}).status_code==403


def test_csrf_tampered_cookie_and_token(config,key):
    with client_for(app_for(config,key)) as c:
        token=csrf(c)
        c.cookies.set('rm_admin_csrf','forged')
        assert c.post('/write',headers={'X-RM-CSRF':'forged'}).status_code==403
        assert c.post('/write',headers={'X-RM-CSRF':token}).status_code==403


def test_headers_and_secure_cookie(config,key):
    with client_for(app_for(config,key),True,key) as c:
        r=c.get('/')
        cookie=r.headers['set-cookie']
        assert '__Host-rm_admin_csrf=' in cookie
        assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie
        assert 'Domain=' not in cookie
        for h in ['cache-control','content-security-policy','x-frame-options','x-content-type-options','referrer-policy','permissions-policy','strict-transport-security']:
            assert r.headers[h]
        assert r.headers['cache-control']=='private, no-store'


def test_ical_only_host_is_preserved(config,key):
    with client_for(app_for(config,key)) as c:
        assert c.get('/ical/rooms/token/platform.ics',headers={'Host':'calendarios.hsi-rents.com'}).status_code==200
        for path in ['/','/persons','/docs','/ical/../persons']:
            assert c.get(path,headers={'Host':'calendarios.hsi-rents.com'}).status_code==404
        assert c.post('/ical/rooms/token/platform.ics',headers={'Host':'calendarios.hsi-rents.com'}).status_code==404


def test_audit_contains_no_request_secrets(config,key):
    class Sink:
        def __init__(self):self.rows=[]
        def emit(self,event,**fields):self.rows.append((event,fields))
    sink=Sink()
    with client_for(app_for(config,key,sink),True,key) as c:
        c.get('/?secret=private-needle')
        c.get('/private-needle',headers={'Cf-Access-Jwt-Assertion':'private-needle'})
    data=json.dumps(sink.rows)
    assert 'private-needle' not in data and 'owner@example.test' not in data and signed(key) not in data
    assert 'remote_read' in data and 'access_denied' in data


def test_jwks_cache_throttle_rotation_and_outage(config,key):
    async def exercise():
        now=[1000];calls=[];good=verifier(config,key).fetch
        async def fetch():calls.append(1);return await good()
        v=AccessVerifier(config,fetch=fetch,clock=lambda:now[0])
        await asyncio.gather(*[v.verify(signed(key)) for _ in range(10)])
        assert len(calls)==1
        payload=jwt.decode(signed(key),options={'verify_signature':False})
        unknown=jwt.encode(payload,key,algorithm='RS256',headers={'kid':'rotated'})
        with pytest.raises(AccessDenied):await v.verify(unknown)
        assert len(calls)==1
        now[0]+=31
        async def rotated():
            result=await good();result['keys'][0]['kid']='rotated';return result
        v.fetch=rotated
        await v.verify(unknown)
        now[0]+=301
        async def unavailable():raise TimeoutError('sensitive-provider-detail')
        v.fetch=unavailable
        with pytest.raises(AccessDenied):await v.verify(unknown)
    asyncio.run(exercise())


def test_configuration_fail_closed():
    with pytest.raises(ValueError):AccessConfig(True)
    with pytest.raises(ValueError):AccessConfig(True,'admin.example.test','http://evil.test','aud',('a',))


def test_real_admin_screens_readonly_database_and_local_write(db_session,config,key,monkeypatch):
    from backend.app_factory import create_app
    from backend.models.person import Person
    from backend.models.booking import Booking
    from backend.models.owner import Owner
    from tests.integration.api.test_bookings_routes import create_room
    from backend.core import admin_security_database as secure_db
    room=create_room(db_session)
    person=Person(full_name='Synthetic remote test',active=True)
    owner=Owner(legal_name='Synthetic owner',active=True)
    db_session.add_all([person,owner]);db_session.flush()
    booking=Booking(room_id=room.id,source_guest_name='Synthetic remote test',check_in=date(2026,12,1),check_out=date(2027,1,1),price=350,origin='manual')
    db_session.add(booking);db_session.commit()
    monkeypatch.setattr(secure_db,'engine',db_session.get_bind())
    app=create_app()
    for m in app.user_middleware:
        if m.cls is AdminSecurityMiddleware:m.kwargs.update(config=config,verifier=verifier(config,key))
    paths=['/','/gantt/','/properties/',f'/rooms/{room.id}','/persons',f'/persons/{person.id}',
           '/owners',f'/owners/{owner.id}','/expenses','/settlements',f'/bookings/{booking.id}/finance',f'/bookings/{booking.id}']
    before={table:db_session.execute(text(f'SELECT count(*) FROM {table}')).scalar() for table in ['persons','bookings','payments','owner_payouts']}
    with client_for(app,True,key) as c:
        for path in paths:
            response=c.get(path)
            assert response.status_code==200,(path,response.text[:200])
            if response.headers.get('content-type','').startswith('text/html'):
                assert 'http://admin.example.test' not in response.text
        token=csrf(c)
        response=c.post('/bookings/person-search',data={'query':'Synthetic','_rm_csrf':token})
        # Tenant reuse is a separate checkpoint. Its real handler is tested
        # when installed; the allowed POST capability is always tested above.
        if '/bookings/person-search' in app.openapi()['paths']:
            assert response.status_code==200
        else:
            assert response.status_code in {404,405}
        assert c.post('/persons/create',data={'full_name':'SHOULD NOT EXIST','_rm_csrf':token}).status_code==403
    after={table:db_session.execute(text(f'SELECT count(*) FROM {table}')).scalar() for table in before}
    assert before==after
    with db_session.get_bind().connect() as connection:
        assert connection.exec_driver_sql('PRAGMA query_only').scalar()==0
        assert connection.exec_driver_sql('PRAGMA quick_check').scalar()=='ok'
        assert connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()==[]


def test_readonly_dependency_blocks_accidental_write(db_session,monkeypatch):
    from backend.core import admin_security_database as secure_db
    monkeypatch.setattr(secure_db,'engine',db_session.get_bind())
    scope={'type':'http','state':{'admin_remote':True}}
    generator=secure_db.admin_get_db(Request(scope));session=next(generator)
    from sqlalchemy.exc import OperationalError
    with pytest.raises(OperationalError):session.execute(text("INSERT INTO persons(full_name,active) VALUES('blocked',1)"))
    generator.close()
    with db_session.get_bind().connect() as connection:
        assert connection.exec_driver_sql('PRAGMA query_only').scalar()==0


def test_valid_token_cannot_assign_identity_on_local_host(config,key):
    with client_for(app_for(config,key)) as c:
        assert c.get('/',headers={'Cf-Access-Jwt-Assertion':signed(key)}).status_code==403


def test_unsigned_email_does_not_override_signed_identity(config,key):
    with client_for(app_for(config,key),True,key) as c:
        token=csrf(c)
        response=c.post('/bookings/person-search',headers={'Cf-Access-Authenticated-User-Email':'attacker@example.test','X-RM-CSRF':token},data={'query':'x'})
        assert response.json()['identity']['email']=='owner@example.test'


def test_every_existing_write_route_is_denied_remotely(config,key):
    from backend.app_factory import create_app
    from backend.core.admin_read_policy import READ_POSTS
    app=create_app()
    for m in app.user_middleware:
        if m.cls is AdminSecurityMiddleware:m.kwargs.update(config=config,verifier=verifier(config,key))
    checked=0
    with client_for(app,True,key) as c:
        for template, operations in app.openapi()['paths'].items():
            for method in {m.upper() for m in operations} & {'POST','PUT','PATCH','DELETE'}:
                path=re.sub(r'\{[^}]+\}','1',template)
                if method=='POST' and path in READ_POSTS:continue
                assert c.request(method,path).status_code==403,(method,path)
                checked+=1
    assert checked>50


def test_unexpected_remote_error_is_private(config,key):
    app=app_for(config,key)
    @app.get('/persons')
    def broken():raise ValueError('private-secret-never-render')
    with client_for(app,True,key) as c:
        response=c.get('/persons')
        assert response.status_code==503
        assert response.headers['cache-control']=='private, no-store'
        assert 'private-secret' not in response.text


def test_websocket_denied(config,key):
    from starlette.websockets import WebSocketDisconnect
    with client_for(app_for(config,key),True,key) as c:
        with pytest.raises(WebSocketDisconnect):
            with c.websocket_connect('/persons'):pass


def test_invalid_form_tokens_do_not_raise_http_500(config,key):
    with client_for(app_for(config,key)) as c:
        csrf(c)
        for value in ['', 'incorrect', 'ñá🦉']:
            assert c.post('/write',data={'_rm_csrf':value}).status_code==403


def test_cookie_alone_does_not_authenticate(config,key):
    with client_for(app_for(config,key),True,key) as c:
        del c.headers['Cf-Access-Jwt-Assertion']
        c.cookies.set('CF_Authorization',signed(key))
        assert c.get('/').status_code==401


def test_existing_local_booking_form_still_writes_only_with_csrf(client,db_session):
    from tests.integration.api.test_bookings_routes import create_room, booking_data
    from backend.models.booking import Booking
    from sqlalchemy import select
    room=create_room(db_session)
    response=client.post('/bookings/create',data=booking_data(room.id),follow_redirects=False)
    assert response.status_code==303
    booking=db_session.scalar(select(Booking))
    assert booking is not None and booking.room_id==room.id
    assert client.get(f'/bookings/{booking.id}').status_code==200
    assert client.get(f'/rooms/{room.id}').status_code==200
