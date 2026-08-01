from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api.routers import dashboard, gantt, rooms, settings

app = FastAPI(
    title="RentalManager",
    version="1.0.0"
)

app.mount(
    "/static",
    StaticFiles(directory="backend/static"),
    name="static"
)

app.include_router(dashboard.router)
app.include_router(gantt.router)
app.include_router(rooms.router)
app.include_router(settings.router)
