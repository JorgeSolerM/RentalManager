"""Local-only health and opt-in ASGI request diagnostics. No business writes."""
import asyncio
from contextlib import closing
import ipaddress
import os
from pathlib import Path
import sqlite3
import time
from urllib.parse import urlsplit
import uuid

from starlette.responses import JSONResponse

from backend.core.operational_logging import configured_sink, normalized_route, error_kind


def local_request(scope):
    try:
        if not ipaddress.ip_address(scope['client'][0]).is_loopback: return False
        headers = scope.get('headers', [])
        # Never allow reverse-proxy requests, even with forged loopback forwarding.
        if any(k.lower() in {b'forwarded', b'x-forwarded-for', b'x-forwarded-host', b'x-forwarded-proto'} for k,v in headers):
            return False
        hosts = [v.decode('ascii') for k,v in headers if k.lower()==b'host']
        return len(hosts)==1 and urlsplit('//'+hosts[0]).hostname in {'localhost','127.0.0.1','::1'}
    except (ValueError, KeyError, TypeError, UnicodeError):
        return False


def read_dependencies(database_path, cache_path=None, timeout=.35):
    """Actual bounded SQLite reads; mode=ro cannot create a missing database."""
    for path, sql in ((database_path, 'SELECT name FROM sqlite_master LIMIT 1'),
                      (cache_path, 'SELECT status FROM locations LIMIT 1')):
        if path is None: continue
        deadline = time.monotonic()+timeout
        with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro', uri=True, timeout=timeout)) as db:
            db.execute('PRAGMA query_only=ON')
            db.set_progress_handler(lambda: int(time.monotonic()>deadline), 100)
            db.execute(sql).fetchone()
    return True


class OperationalMiddleware:
    def __init__(self, app, *, sink, database_path, cache_path=None, probe=None, readiness_timeout=1):
        self.app, self.sink = app, sink
        self.database_path, self.cache_path = database_path, cache_path
        self.probe = probe or (lambda: read_dependencies(self.database_path, self.cache_path))
        self.readiness_timeout = readiness_timeout
        self.pending = None
        self.last_check = 0
        self.last_ready = False

    async def ready(self):
        if self.pending is None and time.monotonic()-self.last_check<1:
            return self.last_ready
        if self.pending is None:
            async def run():
                try: return bool(await asyncio.to_thread(self.probe))
                except Exception: return False
            self.pending = asyncio.create_task(run())
        task = self.pending
        try:
            ready = await asyncio.wait_for(asyncio.shield(task),timeout=self.readiness_timeout)
            self.last_check, self.last_ready = time.monotonic(), ready
            if self.pending is task: self.pending = None
            return ready
        except asyncio.TimeoutError:
            # Keep one in-flight probe; repeated requests cannot create unbounded workers.
            return False

    async def __call__(self, scope, receive, send):
        if scope['type']!='http': return await self.app(scope, receive, send)
        if scope.get('path','').startswith('/_ops/'):
            path = scope['path']
            if not local_request(scope) or path not in {'/_ops/live','/_ops/ready','/_ops/logging'}:
                return await JSONResponse({'detail':'Not Found'},status_code=404)(scope,receive,send)
            if scope['method'] not in {'GET','HEAD'}:
                return await JSONResponse({'detail':'Method Not Allowed'},status_code=405)(scope,receive,send)
            if path == '/_ops/logging':
                info = {'enabled': self.sink is not None}
                if self.sink:
                    info.update(dropped=self.sink.dropped, write_failures=self.sink.write_failures,
                                queued=self.sink.queue.qsize())
                return await JSONResponse(info, headers={'Cache-Control':'no-store','X-Robots-Tag':'noindex'})(scope,receive,send)
            ready = True if path=='/_ops/live' else await self.ready()
            if path=='/_ops/ready' and self.sink:
                self.sink.emit('dependency_check',ready=ready)
            response=JSONResponse({'status':'ok' if ready else 'unavailable'},status_code=200 if ready else 503,
                headers={'Cache-Control':'no-store','X-Robots-Tag':'noindex'})
            return await response(scope,receive,send)
        if not self.sink: return await self.app(scope,receive,send)
        request_id = uuid.uuid4().hex  # Never accept a client identifier as log data.
        started = time.monotonic()
        base = {'request_id':request_id,'method':scope['method']}
        self.sink.emit('request_started',route=normalized_route(scope),**base)
        status = 500
        async def wrapped_send(message):
            nonlocal status
            if message['type']=='http.response.start':
                status=message['status']
                message=dict(message)
                message['headers']=list(message.get('headers',[]))+[(b'x-request-id',request_id.encode('ascii'))]
            await send(message)
        try:
            await self.app(scope,receive,wrapped_send)
        except BaseException as error:
            self.sink.emit('request_failed',route=normalized_route(scope),status=status,
                duration_ms=(time.monotonic()-started)*1000,error_type=error_kind(error),**base)
            raise
        else:
            self.sink.emit('request_finished',route=normalized_route(scope),status=status,
                duration_ms=(time.monotonic()-started)*1000,**base)


def install_diagnostics(app, service):
    if os.getenv('RM_DIAGNOSTICS_ENABLED','0')!='1': return
    from backend.database.session import DATABASE_PATH
    from backend.public.map_locations import cache_path, map_enabled
    # Explicit shared cache is required for admin incidents; public needs it only with map enabled.
    cache = cache_path() if (os.getenv('PUBLIC_GEOCODING_CACHE') or (service=='public' and map_enabled())) else None
    sink = configured_sink(service)
    app.state.operational_sink = sink
    app.add_middleware(OperationalMiddleware,sink=sink,database_path=DATABASE_PATH,cache_path=cache)
