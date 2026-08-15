from fastapi.staticfiles import StaticFiles

import backend.app_factory as app_factory
from backend.api.routers import rooms


def test_create_app_without_initialization_registers_expected_application_parts(
    monkeypatch,
):
    def initialization_must_not_run():
        raise AssertionError("init_db must not run when initialize_database is False")

    monkeypatch.setattr(app_factory, "init_db", initialization_must_not_run)

    app = app_factory.create_app(initialize_database=False)
    paths = set(app.openapi()["paths"])

    assert app.title == "RentalManager - HSI Rents"
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
