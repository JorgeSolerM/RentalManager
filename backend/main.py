from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.core.jinja_filters import format_date
from backend.database.init_db import init_db

from backend.api.routers import (
    dashboard,
    gantt,
    properties,
    rooms,
    settings,
    bookings,
)

app = FastAPI(
    title="RentalManager - HSI Rents",
    version="1.0.0",
)

init_db()

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

# ----------------------------------------------------
# Filtros Jinja
# ----------------------------------------------------

rooms.templates.env.filters["date"] = format_date
