import asyncio
import json
import sqlite3
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.core.operational_diagnostics import OperationalMiddleware, read_dependencies
from backend.core.operational_logging import EventSink


def app_for(tmp_path,probe=lambda:True,sink=None,timeout=.1):
    app=FastAPI()
    @app.get('/ical/rooms/{token}/{platform}.ics')
    def calendar(token:str,platform:str):return {'ok':True}
    @app.get('/boom')
    def boom():raise ValueError('synthetic-secret bank-account user@example.test')
    app.add_middleware(OperationalMiddleware,sink=sink,database_path=tmp_path/'db.sqlite3',
        probe=probe,readiness_timeout=timeout)
    return app


def test_local_liveness_readiness_no_sensitive_details(tmp_path):
    def failing():raise sqlite3.OperationalError('PRIVATE path')
    with TestClient(app_for(tmp_path,failing),base_url='http://127.0.0.1',client=('127.0.0.1',1)) as client:
        assert client.get('/_ops/live').json()=={'status':'ok'}
        r=client.get('/_ops/ready');assert r.status_code==503 and r.json()=={'status':'unavailable'}
        assert client.post('/_ops/live').status_code==405
        assert client.get('/_ops/unknown').status_code==404
        assert client.get('/_ops/logging').json()=={'enabled':False}


@pytest.mark.parametrize('headers',[{'Host':'hsi-rents.com'},{'X-Forwarded-For':'127.0.0.1'},
    {'Forwarded':'for=127.0.0.1'},{'X-Forwarded-Host':'localhost'},{'Host':'attacker.example'}])
def test_proxy_or_external_host_cannot_reveal_health(tmp_path,headers):
    with TestClient(app_for(tmp_path),base_url='http://127.0.0.1',client=('127.0.0.1',1)) as client:
        assert client.get('/_ops/live',headers=headers).status_code==404
        assert client.get('/_ops/logging',headers=headers).status_code==404
    with TestClient(app_for(tmp_path),base_url='http://127.0.0.1',client=('192.0.2.2',1)) as client:
        assert client.get('/_ops/live').status_code==404


def test_slow_probe_bounded_and_single_flight(tmp_path):
    calls=[]
    def slow():calls.append(1);time.sleep(.25);return True
    with TestClient(app_for(tmp_path,slow,timeout=.02),base_url='http://127.0.0.1',client=('127.0.0.1',1)) as client:
        t=time.monotonic()
        for _ in range(3):assert client.get('/_ops/ready').status_code==503
        assert time.monotonic()-t<.2 and len(calls)==1
        assert client.get('/_ops/live').status_code==200
        time.sleep(.25)
        assert client.get('/_ops/ready').status_code==200 and len(calls)==1


def test_sqlite_readiness_does_not_create_or_mutate_files(tmp_path):
    missing=tmp_path/'missing.sqlite3'
    with pytest.raises(sqlite3.Error):read_dependencies(missing)
    assert not missing.exists()
    db=tmp_path/'business.sqlite3';cache=tmp_path/'cache.sqlite3'
    with sqlite3.connect(db) as c:c.execute('create table sentinel(id integer)')
    with sqlite3.connect(cache) as c:c.execute('create table locations(status text)')
    before=[p.read_bytes() for p in (db,cache)]
    assert read_dependencies(db,cache)
    assert before==[p.read_bytes() for p in (db,cache)]
    with sqlite3.connect(db) as lock:
        lock.execute('BEGIN EXCLUSIVE')
        t=time.monotonic()
        with pytest.raises(sqlite3.Error):read_dependencies(db,timeout=.03)
        assert time.monotonic()-t<.3


def test_http_privacy_correlation_errors_and_unmatched_paths(tmp_path):
    sink=EventSink(tmp_path,'admin','a'*40)
    with TestClient(app_for(tmp_path,sink=sink),base_url='http://127.0.0.1',client=('127.0.0.1',1),raise_server_exceptions=False) as client:
        r=client.get('/ical/rooms/private-token/secret-platform.ics?password=sensitive-query',
            headers={'Authorization':'Bearer secret-auth','Cookie':'session=secret-cookie','X-Request-ID':'attacker-value'})
        assert r.status_code==200 and len(r.headers['x-request-id'])==32
        assert client.get('/private-unmatched-email@example.test').status_code==404
        assert client.get('/boom').status_code==500
    assert sink.flush();sink.close()
    text=(tmp_path/'admin.jsonl').read_text()
    for secret in ['private-token','secret-platform','sensitive-query','secret-auth','secret-cookie',
                   'attacker-value','private-unmatched-email','synthetic-secret','bank-account','user@example.test']:
        assert secret not in text
    rows=[json.loads(line) for line in text.splitlines()]
    end=next(x for x in rows if x['event']=='request_finished' and x['status']==200)
    assert end['route']=='/ical/rooms/{token}/{platform}.ics'
    assert sum(x.get('request_id')==end['request_id'] for x in rows)==2
    assert any(x['event']=='request_failed' for x in rows)


def test_factory_disabled_by_default(monkeypatch):
    monkeypatch.delenv('RM_DIAGNOSTICS_ENABLED',raising=False)
    from backend.app_factory import create_app
    from backend.public.app_factory import create_public_app
    for app in (create_app(),create_public_app()):
        assert not any(m.cls is OperationalMiddleware for m in app.user_middleware)


def test_factories_opt_in_use_separate_logs_and_readonly_dependencies(tmp_path,monkeypatch):
    import logging
    from backend.core import operational_logging as ops
    from backend.database import session
    from backend.app_factory import create_app
    from backend.public.app_factory import create_public_app
    db=tmp_path/'synthetic.sqlite3'
    with sqlite3.connect(db) as c:c.execute('create table marker(id integer)')
    monkeypatch.setattr(session,'DATABASE_PATH',db)
    monkeypatch.setattr(ops,'_sinks',{})
    monkeypatch.setenv('RM_DIAGNOSTICS_ENABLED','1')
    monkeypatch.setenv('RM_DIAGNOSTICS_LOG_DIR',str(tmp_path/'logs'))
    monkeypatch.delenv('PUBLIC_GEOCODING_CACHE',raising=False)
    monkeypatch.setenv('PUBLIC_MAP_ENABLED','0')
    loggers=[logging.getLogger(),logging.getLogger('uvicorn.error')]
    before=[list(logger.handlers) for logger in loggers]
    try:
        for app in (create_app(initialize_database=False),create_public_app()):
            with TestClient(app,base_url='http://127.0.0.1',client=('127.0.0.1',1)) as client:
                assert client.get('/_ops/live').status_code==200
                assert client.get('/_ops/ready').status_code==200
                assert client.get('/_ops/logging').json()['enabled'] is True
        for sink in ops._sinks.values():assert sink.flush()
        assert (tmp_path/'logs/admin.jsonl').exists()
        assert (tmp_path/'logs/public.jsonl').exists()
    finally:
        for sink in ops._sinks.values():sink.close()
        for logger,handlers in zip(loggers,before):logger.handlers=handlers
