from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api.routers import (
    bookings,
    dashboard,
    gantt,
    properties,
    rooms,
    settings,
)
from backend.core.jinja_filters import format_date


def create_app(initialize_database: bool = False) -> FastAPI:
    """Create the application without creating or migrating database schema."""
    app = FastAPI(
        title="RentalManager - HSI Rents",
        version="1.0.0",
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

    rooms.templates.env.filters["date"] = format_date

    return app
