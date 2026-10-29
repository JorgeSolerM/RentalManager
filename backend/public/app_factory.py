from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from backend.core.config import get_public_site_allowed_hosts, get_public_site_name
from backend.core.media_storage import MediaFileStore
from backend.public.router import router
from backend.public.collaborator_calendar import router as collaborator_router, PREFIX as COLLABORATOR_PREFIX


def create_public_app(*, media_store: MediaFileStore | None = None) -> FastAPI:
    app = FastAPI(
        title=get_public_site_name(),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        debug=False,
    )
    app.state.public_media_store = media_store or MediaFileStore()
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=get_public_site_allowed_hosts(),
    )
    app.mount(
        "/static",
        StaticFiles(directory="backend/public/static"),
        name="public_static",
    )

    @app.middleware("http")
    async def public_security_headers(request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; object-src 'none'; base-uri 'self'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        if request.url.path.startswith(COLLABORATOR_PREFIX):
            response.headers['Referrer-Policy'] = 'no-referrer'
            response.headers['Cache-Control'] = 'private, no-store, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
            response.headers['Vary'] = 'Authorization'
        return response

    app.include_router(router)
    app.include_router(collaborator_router)
    return app
