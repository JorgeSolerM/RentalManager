import re
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from backend.api.routers import (
    bookings,
    dashboard,
    gantt,
    master_calendars,
    photos,
    properties,
    room_calendars,
    rooms,
    settings,
    persons,
    booking_finance,
)
from backend.core.jinja_filters import format_date
from backend.core.logging import configure_sensitive_url_logging
from backend.core.config import APP_VERSION


BOOKING_FORM_PATH = re.compile(
    r"^/bookings/(?:create|update/\d+|update-imported-local/\d+)$"
)
ROOM_REFERER_PATH = re.compile(r"^/rooms/\d+$")


def create_app(initialize_database: bool = False) -> FastAPI:
    """Create the application without creating or migrating database schema."""
    configure_sensitive_url_logging()
    app = FastAPI(
        title="RentalManager - HSI Rents",
        version=APP_VERSION,
    )

    @app.exception_handler(RequestValidationError)
    async def booking_form_validation_error(request, exc):
        """Return booking form errors to the workspace instead of raw JSON."""
        referer = request.headers.get("referer", "")
        referer_path = urlsplit(referer).path
        if (
            request.method == "POST"
            and BOOKING_FORM_PATH.fullmatch(request.url.path)
            and ROOM_REFERER_PATH.fullmatch(referer_path)
        ):
            return RedirectResponse(
                f"{referer_path}?error=booking_form_invalid", status_code=303
            )
        return await request_validation_exception_handler(request, exc)

    app.mount(
        "/static",
        StaticFiles(directory="backend/static"),
        name="static",
    )

    app.include_router(dashboard.router)
    app.include_router(gantt.router)
    app.include_router(properties.router)
    app.include_router(rooms.router)
    app.include_router(settings.router)
    app.include_router(persons.router)
    app.include_router(bookings.router)
    app.include_router(booking_finance.router)
    app.include_router(room_calendars.router)
    app.include_router(master_calendars.router)
    app.include_router(photos.router)

    rooms.templates.env.filters["date"] = format_date
    dashboard.templates.env.filters["date"] = format_date

    return app
