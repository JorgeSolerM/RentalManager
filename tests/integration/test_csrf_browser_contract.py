import re
import pytest
from fastapi.testclient import TestClient
from tests.integration.test_admin_remote_security import app_for, config, key, client_for, csrf

@pytest.mark.parametrize('origin', ['null', 'http://localhost', 'https://evil.example'])
def test_opaque_and_foreign_origins_still_rejected(config,key,origin):
    app=app_for(config,key)
    with client_for(app) as c:
        token=csrf(c)
        r=c.post('/write',data={'_rm_csrf':token},headers={'Origin':origin})
        assert r.status_code==403 and app.state.writes==0

def test_document_error_is_html_without_reflecting_input(config,key):
    app=app_for(config,key)
    with client_for(app) as c:
        csrf(c)
        r=c.post('/write',data={'_rm_csrf':'invalid','private':'SECRET-SYNTHETIC'},headers={'Accept':'text/html','Sec-Fetch-Dest':'document'})
        assert r.status_code==403 and r.headers['content-type'].startswith('text/html')
        assert 'Volver al formulario' in r.text and 'href="/"' in r.text
        assert 'SECRET-SYNTHETIC' not in r.text
        assert r.headers['cache-control']=='private, no-store'
        assert app.state.writes==0

def test_api_error_remains_json(config,key):
    with client_for(app_for(config,key)) as c:
        csrf(c)
        r=c.post('/write',headers={'Accept':'application/json','Sec-Fetch-Dest':'empty'})
        assert r.status_code==403 and r.json()['code']=='csrf_denied'

def test_native_form_with_exact_origin_retains_body(config,key):
    app=app_for(config,key)
    with client_for(app) as c:
        token=csrf(c)
        r=c.post('/write',data={'_rm_csrf':token,'value':'kept'},headers={'Origin':'http://127.0.0.1','Sec-Fetch-Site':'same-origin'})
        assert r.status_code==200 and r.json()['form']['value']=='kept'
        assert r.headers['referrer-policy']=='same-origin'

def test_base_template_uses_matching_policy(client):
    r=client.get('/')
    assert '<meta name="referrer" content="same-origin">' in r.text
    assert r.headers['referrer-policy']=='same-origin'


def test_csrf_age_origin_and_restart_contract(config,monkeypatch):
    from backend.core.admin_security import AdminSecurityMiddleware
    import backend.core.admin_security as module
    from fastapi import FastAPI
    middleware=AdminSecurityMiddleware(FastAPI(),config=config)
    now=module.time.time()
    monkeypatch.setattr(module.time,'time',lambda:now)
    token=middleware.csrf('http://127.0.0.1:8000')
    assert middleware.valid_csrf(token,'http://127.0.0.1:8000')
    assert not middleware.valid_csrf(token,'http://127.0.0.1:8001')
    assert not AdminSecurityMiddleware(FastAPI(),config=config).valid_csrf(token,'http://127.0.0.1:8000')
    monkeypatch.setattr(module.time,'time',lambda:now+7201)
    assert not middleware.valid_csrf(token,'http://127.0.0.1:8000')
    monkeypatch.setattr(module.time,'time',lambda:now-60)
    assert not middleware.valid_csrf(token,'http://127.0.0.1:8000')

def test_local_http_cookie_flags(config,key):
    with client_for(app_for(config,key)) as c:
        r=c.get('/')
        cookie=r.headers['set-cookie'].lower()
        assert 'httponly' in cookie and 'samesite=strict' in cookie
        assert 'max-age=7200' in cookie and 'path=/' in cookie
        assert '; secure' not in cookie
