from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api.routers import (
    bookings,
    dashboard,
    gantt,
    master_calendars,
    properties,
    room_calendars,
    rooms,
    settings,
)
from backend.core.jinja_filters import format_date
from backend.core.logging import configure_sensitive_url_logging
from backend.core.config import APP_VERSION


def create_app(initialize_database: bool = False) -> FastAPI:
    """Create the application without creating or migrating database schema."""
    configure_sensitive_url_logging()
    app = FastAPI(
        title="RentalManager - HSI Rents",
        version=APP_VERSION,
    )

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
    app.include_router(bookings.router)
    app.include_router(room_calendars.router)
    app.include_router(master_calendars.router)

    rooms.templates.env.filters["date"] = format_date

    return app
