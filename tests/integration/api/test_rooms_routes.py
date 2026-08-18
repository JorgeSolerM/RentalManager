from datetime import datetime, timedelta, timezone

from sqlalchemy import event, select

from backend.models.property import Property
from backend.models.room import Room
from backend.models.platform import Platform
from backend.models.room_calendar import RoomCalendar


def create_property(db_session) -> Property:
    property_obj = Property(
        name="Piso Universidad",
        address="Calle Universidad 1",
        city="Elche",
        owner="HSI Rents",
        active=True,
    )
    db_session.add(property_obj)
    db_session.commit()

    return property_obj


def create_room(db_session, property_id: int) -> Room:
    room = Room(
        property_id=property_id,
        code="H01",
        display_order=1,
        base_price=350,
        active=True,
    )
    db_session.add(room)
    db_session.commit()

    return room


def test_create_room_uses_overridden_temporary_database(client, db_session):
    property_obj = create_property(db_session)

    response = client.post(
        "/rooms/create",
        data={
            "property_id": property_obj.id,
            "code": "H01",
            "base_price": "350",
            "square_meters": "12.5",
        },
        follow_redirects=False,
    )

    persisted_room = db_session.scalar(
        select(Room).where(Room.code == "H01")
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/rooms/property/{property_obj.id}?success=room_created"
    )
    assert persisted_room is not None
    assert persisted_room.property_id == property_obj.id


def test_room_listing_and_edit_use_overridden_temporary_database(client, db_session):
    property_obj = create_property(db_session)
    room = create_room(db_session, property_obj.id)

    listing_response = client.get(f"/rooms/property/{property_obj.id}")
    edit_response = client.get(f"/rooms/edit/{room.id}")

    assert listing_response.status_code == 200
    assert "H01" in listing_response.text
    assert '<th class="room-platforms-column">Plataformas</th>' in listing_response.text
    assert "room-platform-icon" not in listing_response.text
    assert edit_response.status_code == 200
    assert edit_response.json()["id"] == room.id
    assert edit_response.json()["property_id"] == property_obj.id


def test_room_workspace_uses_overridden_temporary_database(client, db_session):
    property_obj = create_property(db_session)
    room = create_room(db_session, property_obj.id)

    response = client.get(f"/rooms/{room.id}")

    assert response.status_code == 200
    assert "Reservas" in response.text
    assert "H01" in response.text


def test_room_listing_shows_compact_ordered_platform_health_without_secrets(
    client, db_session
):
    property_obj = create_property(db_session)
    room = create_room(db_session, property_obj.id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    platforms = [
        Platform(name="Zulu", slug="zulu", favicon="/static/zulu.ico", active=True),
        Platform(name="Alpha", slug="alpha", favicon=None, active=True),
        Platform(name="Beta", slug="beta", favicon="/static/beta.ico", active=True),
        Platform(name="Delta", slug="delta", favicon=None, active=True),
        Platform(name="Gamma", slug="gamma", favicon=None, active=True),
        Platform(name="Inactive", slug="inactive", favicon=None, active=True),
        Platform(name="Not configured", slug="absent", favicon=None, active=True),
        Platform(name="Eta", slug="eta", favicon="/static/eta.ico", active=True),
    ]
    db_session.add_all(platforms)
    db_session.flush()
    calendars = [
        RoomCalendar(
            room_id=room.id, platform_id=platforms[0].id, active=True,
            automatic_sync_enabled=True, last_sync_at=now,
            last_sync_attempt_at=now, last_sync_status="ok",
            master_calendar_first_request_at=now - timedelta(minutes=20),
            last_master_calendar_request_at=now,
            master_calendar_request_count=2,
            import_url="https://secret.example/ZULU_TOKEN.ics",
        ),
        RoomCalendar(
            room_id=room.id, platform_id=platforms[1].id, active=True,
            automatic_sync_enabled=True, last_sync_at=None,
            last_sync_attempt_at=None, import_url="https://example.test/a.ics",
        ),
        RoomCalendar(
            room_id=room.id, platform_id=platforms[2].id, active=True,
            automatic_sync_enabled=True, last_sync_at=now,
            last_sync_attempt_at=now, last_sync_status="error",
            import_url="https://example.test/b.ics",
        ),
        RoomCalendar(
            room_id=room.id, platform_id=platforms[3].id, active=True,
            automatic_sync_enabled=False, last_sync_at=now,
            last_sync_attempt_at=now, last_sync_status="ok",
            import_url="https://example.test/d.ics",
        ),
        RoomCalendar(
            room_id=room.id, platform_id=platforms[4].id, active=True,
            automatic_sync_enabled=True, last_sync_at=datetime(2020, 1, 1),
            last_sync_attempt_at=datetime(2020, 1, 1), last_sync_status="ok",
            import_url="https://example.test/g.ics",
        ),
        RoomCalendar(
            room_id=room.id, platform_id=platforms[5].id, active=False,
            automatic_sync_enabled=True, last_sync_at=now,
            last_sync_attempt_at=now, last_sync_status="ok",
            import_url="https://example.test/i.ics",
        ),
        RoomCalendar(
            room_id=room.id, platform_id=platforms[7].id, active=True,
            automatic_sync_enabled=True, last_sync_at=now,
            last_sync_attempt_at=now, last_sync_status="warning",
            master_calendar_first_request_at=datetime(2020, 1, 1),
            last_master_calendar_request_at=datetime(2020, 1, 2),
            master_calendar_request_count=2,
            import_url="https://example.test/e.ics",
        ),
    ]
    db_session.add_all(calendars)
    db_session.commit()

    response = client.get(f"/rooms/property/{property_obj.id}")
    html = response.text

    assert response.status_code == 200
    assert '<th class="room-platforms-column">Plataformas</th>' in html
    assert "Zulu &middot; Sincronizado &middot; Calendario maestro consultado recientemente" in html
    assert "Alpha &middot; Nunca sincronizado &middot; Aún no se han observado consultas externas" in html
    assert "Beta &middot; Error en última sincronización" in html
    assert "Delta &middot; Automatización pausada" in html
    assert "Gamma &middot; Sincronización atrasada" in html
    assert "Inactive &middot; Calendario inactivo" in html
    assert "Eta &middot; Sincronizado &middot; El calendario maestro dejó de consultarse recientemente" in html
    assert "Not configured" not in html
    assert html.count("room-platform-icon-review") == 6
    assert "/static/zulu.ico" in html
    assert "/static/icons/platform-fallback.svg" in html
    assert html.index("Alpha &middot;") < html.index("Beta &middot;") < html.index("Zulu &middot;")
    assert "secret.example" not in html
    assert "ZULU_TOKEN" not in html


def test_room_listing_platform_loading_has_no_query_per_room(client, db_session):
    property_obj = create_property(db_session)
    platform = Platform(name="Shared", slug="shared", active=True)
    db_session.add(platform)
    db_session.flush()
    for index in range(6):
        room = Room(
            property_id=property_obj.id, code=f"H{index:02}",
            display_order=index, base_price=350, active=True,
        )
        db_session.add(room)
        db_session.flush()
        db_session.add(RoomCalendar(
            room_id=room.id, platform_id=platform.id, active=True,
            automatic_sync_enabled=False,
        ))
    db_session.commit()
    property_id = property_obj.id

    selects = []

    def count_selects(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            selects.append(statement)

    event.listen(db_session.bind, "before_cursor_execute", count_selects)
    try:
        response = client.get(f"/rooms/property/{property_id}")
    finally:
        event.remove(db_session.bind, "before_cursor_execute", count_selects)

    assert response.status_code == 200
    assert len(selects) == 3
    assert response.text.count("Shared &middot; Automatización pausada") == 12


def test_platform_favicons_are_defensively_constrained_to_sixteen_pixels():
    css = open("backend/static/css/main.css", encoding="utf-8").read()
    template = open(
        "backend/templates/pages/rooms.html", encoding="utf-8"
    ).read()
    fallback = open(
        "backend/static/icons/platform-fallback.svg", encoding="utf-8"
    ).read()

    image_rule = css.split(".room-platform-icon img {", 1)[1].split("}", 1)[0]
    container_rule = css.split(".room-platform-icon {", 1)[1].split("}", 1)[0]
    assert "width: 16px" in image_rule
    assert "height: 16px" in image_rule
    assert "max-width: 16px" in image_rule
    assert "max-height: 16px" in image_rule
    assert "width: 20px" in container_rule
    assert "height: 20px" in container_rule
    assert "border: 1px solid" in container_rule
    assert "border-radius: 3px" in container_rule
    assert "background: #fff" in container_rule
    assert "display: block" in image_rule
    assert "object-fit: contain" in image_rule
    assert "flex-wrap: nowrap" in css
    assert template.count('width="16" height="16"') == 2
    assert 'width="16" height="16" viewBox=' in fallback


def test_priority_platform_favicon_assets_are_public_and_keep_health_css(client):
    paths = (
        "/static/icons/platforms/housinganywhere.svg",
        "/static/icons/platforms/flatio.svg",
        "/static/icons/platforms/spotahome.png",
    )
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        assert response.content

    css = open("backend/static/css/main.css", encoding="utf-8").read()
    review_rule = css.split(".room-platform-icon-review img {", 1)[1].split("}", 1)[0]
    assert "filter: grayscale(100%)" in review_rule
