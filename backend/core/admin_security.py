"""Admin-only host/Access/read-capability/CSRF boundary. Fail closed remotely."""
import hashlib
import hmac
import re
import secrets
import time
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, HTMLResponse

from backend.core.admin_access import AccessConfig, AccessDenied, AccessVerifier, host_header, loopback
from backend.core.admin_read_policy import permits
from backend.core.operational_logging import configured_sink, normalized_route

PROXY_HEADERS = {'forwarded', 'x-forwarded-for', 'x-forwarded-host', 'x-forwarded-proto',
                 'cf-connecting-ip', 'cf-access-jwt-assertion', 'cf-access-authenticated-user-email'}
SAFE = {'GET', 'HEAD', 'OPTIONS'}
CSRF_COOKIE = 'rm_admin_csrf'
REMOTE_CSRF_COOKIE = '__Host-rm_admin_csrf'

CSRF_ERROR_HTML = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Formulario no enviado · RentalManager</title>
<style>body{font:1rem system-ui;margin:3rem auto;padding:0 1rem;max-width:42rem;line-height:1.6}button,a{font:inherit}button{padding:.6rem 1rem;margin-right:1rem}</style></head>
<body><main><h1>No se ha guardado el formulario</h1><p role="alert">El formulario ha caducado o no es válido.</p>
<p>Vuelve al formulario y conserva los datos que necesites antes de recargar la página. Después vuelve a enviarlo.</p>
<button type="button" onclick="history.back()">Volver al formulario</button><a href="/">Ir al inicio</a>
<p>No se ha realizado ninguna operación con este envío.</p></main></body></html>"""


class AdminSecurityMiddleware(BaseHTTPMiddleware):
    async def __call__(self, scope, receive, send):
        if scope['type'] == 'websocket':
            # No administrative websocket capability has been approved.
            await send({'type': 'websocket.close', 'code': 1008})
            return
        return await super().__call__(scope, receive, send)

    def __init__(self, app, *, config=None, verifier=None, sink=None):
        super().__init__(app)
        self.config = config or AccessConfig.from_env()
        self.verifier = verifier or AccessVerifier(self.config)
        self.secret = secrets.token_bytes(32)
        self.sink = sink or configured_sink('admin')

    def csrf(self, origin):
        value = f'{int(time.time())}.{secrets.token_urlsafe(32)}'
        return value + '.' + hmac.new(self.secret, (origin + ':' + value).encode(), hashlib.sha256).hexdigest()

    def valid_csrf(self, token, origin):
        try:
            stamp, nonce, mac = token.split('.')
            value = stamp + '.' + nonce
            return (0 <= time.time() - int(stamp) <= 7200 and len(nonce) == 43 and
                    hmac.compare_digest(mac, hmac.new(self.secret, (origin + ':' + value).encode(), hashlib.sha256).hexdigest()))
        except (ValueError, TypeError, AttributeError):
            return False

    def record(self, request, code, status):
        if self.sink:
            try:
                self.sink.emit('admin_access', result_code=code, status=status,
                               method=request.method, route=normalized_route(request.scope))
            except Exception:
                pass

    @staticmethod
    def headers(response, remote):
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['Pragma'] = 'no-cache'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        # no-referrer makes native form POSTs carry Origin: null in browsers.
        # Preserve the exact origin locally; never disclose a referrer cross-origin.
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        # Legacy inline scripts/styles are retained; tighten with nonces in a
        # separate UI-compatible change. No arbitrary external script origins.
        response.headers['Content-Security-Policy'] = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data: blob:; "
            "font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
        if remote:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    def reject(self, request, code, status=403, remote=False):
        self.record(request, code, status)
        message = {'csrf_denied': 'El formulario ha caducado o no es válido. Recarga la página y vuelve a intentarlo.',
                   'read_only_denied': 'Acceso remoto de consulta: esta operación no está permitida.'}.get(code, 'Acceso no permitido.')
        if code == 'csrf_denied' and (
            request.headers.get('sec-fetch-dest') == 'document' or
            (not request.headers.get('sec-fetch-dest') and 'text/html' in request.headers.get('accept', '')
             and 'application/json' not in request.headers.get('accept', ''))
        ):
            # Fixed HTML only: never echo form data, tokens or untrusted return URLs.
            return self.headers(HTMLResponse(CSRF_ERROR_HTML, status_code=status), remote)
        return self.headers(JSONResponse({'detail': message, 'code': code}, status_code=status), remote)

    async def dispatch(self, request, call_next):
        config, path = self.config, request.url.path
        try:
            host = host_header(request.headers)
        except (AccessDenied, ValueError):
            return self.reject(request, 'invalid_host', 400)
        # Preserve only the established public ICS export surface, never admin.
        if host in config.ical_hosts:
            if request.method in {'GET', 'HEAD'} and re.fullmatch(r'/ical/rooms/[A-Za-z0-9_-]+/[a-zA-Z0-9_-]+\.ics', path):
                return await call_next(request)
            return self.reject(request, 'ical_route_denied', 404)
        remote = host == config.hostname and bool(config.hostname)
        request.state.admin_remote = remote
        request.state.admin_identity = None
        if remote:
            if not config.enabled:
                return self.reject(request, 'remote_disabled', remote=True)
            # Launch uvicorn with --no-proxy-headers: only this boundary may
            # interpret proxy metadata, after verifying the signed identity.
            if not loopback(request.scope):
                return self.reject(request, 'untrusted_proxy', remote=True)
            if request.headers['host'] not in {config.hostname, config.hostname + ':443'}:
                return self.reject(request, 'invalid_host', remote=True)
            if request.headers.getlist('x-forwarded-proto') != ['https'] or 'forwarded' in request.headers:
                return self.reject(request, 'invalid_proxy', remote=True)
            if request.headers.getlist('x-forwarded-host') not in ([], [config.hostname]):
                return self.reject(request, 'invalid_proxy', remote=True)
            tokens = request.headers.getlist('cf-access-jwt-assertion')
            try:
                if len(tokens) != 1:
                    raise AccessDenied()
                request.state.admin_identity = await self.verifier.verify(tokens[0])
            except AccessDenied:
                return self.reject(request, 'access_denied', 401, remote=True)
            if not permits(request.method, path):
                return self.reject(request, 'read_only_denied', remote=True)
            request.scope['scheme'] = 'https'
            request.scope['headers'] = [(k, v) for k, v in request.scope['headers'] if k.decode().lower() not in PROXY_HEADERS]
        else:
            if host not in config.local_hosts or not loopback(request.scope):
                return self.reject(request, 'invalid_host')
            if any(h in request.headers for h in PROXY_HEADERS):
                return self.reject(request, 'local_spoof_denied')
            if request.method in {'GET', 'HEAD'} and re.fullmatch(r'/ical/rooms/[A-Za-z0-9_-]+/[a-zA-Z0-9_-]+\.ics', path):
                return await call_next(request)
        # Bind the browser's CSRF cookie to this exact origin (including port).
        scheme = 'https' if remote else request.scope.get('scheme', 'http')
        origin = scheme + '://' + request.headers['host']
        if request.method not in SAFE:
            origins = request.headers.getlist('origin')
            if origins and origins != [origin]:
                return self.reject(request, 'csrf_denied', remote=remote)
            if request.headers.get('sec-fetch-site') in {'cross-site', 'same-site'}:
                return self.reject(request, 'csrf_denied', remote=remote)
        cookie_name = REMOTE_CSRF_COOKIE if remote else CSRF_COOKIE
        cookie = request.cookies.get(cookie_name, '')
        valid_cookie = self.valid_csrf(cookie, origin)
        if request.method not in SAFE:
            if not valid_cookie:
                return self.reject(request, 'csrf_denied', remote=remote)
            token = request.headers.get('x-rm-csrf', '')
            if not token and request.headers.get('content-type', '').split(';')[0] in {'application/x-www-form-urlencoded', 'multipart/form-data'}:
                # Limit buffering; arbitrary oversized forms must not exhaust RAM.
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > 32 * 1024 * 1024:
                        return self.reject(request, 'request_too_large', 413, remote)
                request._body = bytes(body)
                try:
                    form = await request.form()
                    values = form.getlist('_rm_csrf')
                    token = values[0] if len(values) == 1 else ''
                except Exception:
                    return self.reject(request, 'csrf_denied', remote=remote)
            if not valid_cookie or not isinstance(token, str) or not token.isascii() or not hmac.compare_digest(cookie, token):
                return self.reject(request, 'csrf_denied', remote=remote)
        request.state.admin_csrf = cookie if valid_cookie else self.csrf(origin)
        try:
            response = await call_next(request)
        except Exception:
            if not remote:
                raise
            return self.reject(request, 'remote_unavailable', 503, remote=True)
        self.headers(response, remote)
        if not valid_cookie and response.headers.get('content-type', '').startswith('text/html'):
            response.set_cookie(cookie_name, request.state.admin_csrf, max_age=7200,
                                secure=remote or scheme == 'https', httponly=True, samesite='strict', path='/')
        self.record(request, 'remote_read' if remote else 'local_access', response.status_code)
        return response


def install_admin_security(app):
    from backend.database.session import get_db
    from backend.core.admin_security_database import admin_get_db
    app.dependency_overrides[get_db] = admin_get_db
    app.add_middleware(AdminSecurityMiddleware)
