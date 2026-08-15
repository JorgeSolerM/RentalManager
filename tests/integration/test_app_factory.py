from fastapi.staticfiles import StaticFiles

import backend.app_factory as app_factory
from backend.api.routers import rooms
from backend.main import app as main_app


def test_create_app_without_initialization_registers_expected_application_parts(
):
    app = app_factory.create_app()
    paths = set(app.openapi()["paths"])

    assert app.title == "RentalManager - HSI Rents"
    assert main_app.title == "RentalManager - HSI Rents"
    assert not hasattr(app_factory, "init_db")
    assert any(
        isinstance(getattr(route, "app", None), StaticFiles)
        and route.path == "/static"
        for route in app.routes
    )
    assert {
        "/",
        "/gantt/",
        "/properties/",
        "/rooms/property/{property_id}",
        "/settings/",
        "/bookings/room/{room_id}",
    }.issubset(paths)
    assert rooms.templates.env.filters["date"](None) == ""
    assert rooms.templates.env.filters["date"]("literal") == "literal"
