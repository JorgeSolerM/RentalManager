from datetime import date

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from icalendar import Calendar
from datetime import datetime

from backend.app_factory import create_app
from backend.database.base import Base
from backend.database.session import get_db
from backend.models.booking import Booking
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar
from backend.models.person import Person
from backend.models.booking_party import BookingParty


def create_room(db_session) -> Room:
    property_obj = Property(
        name="Piso Universidad",
        address="Calle Universidad 1",
        city="Elche",
        owner="HSI Rents",
        active=True,
    )
    db_session.add(property_obj)
    db_session.flush()

    room = Room(
        property_id=property_obj.id,
        code="H01",
        display_order=1,
        base_price=350,
        active=True,
    )
    db_session.add(room)
    db_session.commit()

    return room


def booking_data(room_id: int, **overrides) -> dict:
    data = {
        "room_id": str(room_id),
        "guest_name": "Ana Pérez",
        "check_in": "2026-09-10",
        "check_out": "2026-09-15",
        "price": "450.50",
        "notes": "Reserva de prueba",
    }
    data.update(overrides)
    return data


def test_booking_create_list_and_get_use_overridden_temporary_database(
    client, db_session
):
    room = create_room(db_session)

    create_response = client.post(
        "/bookings/create",
        data=booking_data(room.id),
        follow_redirects=False,
    )
    booking = db_session.scalar(select(Booking))
    list_response = client.get(f"/bookings/room/{room.id}")
    get_response = client.get(f"/bookings/{booking.id}")

    assert create_response.status_code == 303
    assert create_response.headers["location"] == (
        f"/rooms/{room.id}?success=booking_created"
    )
    assert booking is not None
    assert booking.guest_id is None
    assert booking.source_guest_name == "Ana Pérez"
    assert booking.parties[0].role == "unclassified"
    assert booking.parties[0].person.full_name == "Ana Pérez"
    assert booking.check_in == date(2026, 9, 10)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert get_response.status_code == 200
    assert get_response.json() == {
        "id": booking.id,
        "room_id": room.id,
        "guest_name": "Ana Pérez",
        "source_guest_name": "Ana Pérez",
        "parties": [{
            "id": booking.parties[0].id,
            "person_id": booking.parties[0].person_id,
            "person_name": "Ana Pérez",
            "role": "unclassified",
        }],
        "origin": "manual",
        "check_in": "2026-09-10",
        "check_out": "2026-09-15",
        "expected_arrival_date": None,
        "expected_departure_date": None,
        "price": 450.5,
        "notes": "Reserva de prueba",
        "editable": True,
        "external_block_deletable": False,
    }


def test_booking_update_delete_and_not_found_use_overridden_temporary_database(
    client, db_session
):
    room = create_room(db_session)
    client.post("/bookings/create", data=booking_data(room.id))
    booking = db_session.scalar(select(Booking))

    update_response = client.post(
        f"/bookings/update/{booking.id}",
        data=booking_data(
            room.id,
            guest_name="Luis García",
            check_in="2026-10-01",
            check_out="2026-10-03",
            price="300",
            notes="Actualizada",
            expected_arrival_date="2026-09-29",
            expected_departure_date="2026-10-02",
        ),
        follow_redirects=False,
    )
    db_session.refresh(booking)
    assert booking.parties[0].person.full_name == "Ana Pérez"
    assert booking.source_guest_name == "Luis García"
    assert booking.check_in == date(2026, 10, 1)
    assert booking.expected_arrival_date == date(2026, 9, 29)
    assert booking.expected_departure_date == date(2026, 10, 2)

    delete_response = client.post(
        f"/bookings/delete/{booking.id}",
        follow_redirects=False,
    )
    not_found_response = client.get("/bookings/999")

    assert update_response.status_code == 303
    assert update_response.headers["location"] == (
        f"/rooms/{room.id}?success=booking_updated"
    )
    assert delete_response.status_code == 303
    assert delete_response.headers["location"] == (
        f"/rooms/{room.id}?success=booking_deleted"
    )
    assert db_session.get(Booking, booking.id) is None
    assert not_found_response.status_code == 404
    assert not_found_response.json() == {"detail": "Reserva no encontrada."}


def test_manual_guest_only_change_uses_full_contract_and_preserves_other_fields(
    client, db_session
):
    room = create_room(db_session)
    client.post("/bookings/create", data=booking_data(room.id))
    booking = db_session.scalar(select(Booking))
    original = (
        booking.room_id, booking.check_in, booking.check_out,
        booking.price, booking.notes,
    )

    response = client.post(
        f"/bookings/update/{booking.id}",
        data=booking_data(room.id, guest_name="Nombre corregido"),
        follow_redirects=False,
    )

    db_session.refresh(booking)
    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/rooms/{room.id}?success=booking_updated"
    )
    assert booking.parties[0].person.full_name == "Ana Pérez"
    assert booking.source_guest_name == "Nombre corregido"
    assert (
        booking.room_id, booking.check_in, booking.check_out,
        booking.price, booking.notes,
    ) == original


def test_manual_update_contract_still_requires_room_id(client, db_session):
    room = create_room(db_session)
    client.post("/bookings/create", data=booking_data(room.id))
    booking = db_session.scalar(select(Booking))
    payload = booking_data(room.id, guest_name="No debe aplicarse")
    payload.pop("room_id")

    response = client.post(f"/bookings/update/{booking.id}", data=payload)

    assert response.status_code == 422
    db_session.refresh(booking)
    assert booking.parties[0].person.full_name == "Ana Pérez"
    assert booking.source_guest_name == "Ana Pérez"


def test_deleted_manual_booking_disappears_from_workspace_and_gantt(
    client, db_session
):
    room = create_room(db_session)
    client.post(
        "/bookings/create",
        data=booking_data(
            room.id,
            guest_name="Visible antes de borrar",
            check_in="2026-09-10",
            check_out="2026-09-15",
        ),
    )
    booking = db_session.scalar(select(Booking))
    assert "Visible antes de borrar" in client.get(f"/rooms/{room.id}").text
    before = client.get(
        "/gantt/data?start=2026-09-01&end=2026-10-01"
    ).json()
    assert before["properties"][0]["rooms"][0]["bookings"][0]["id"] == booking.id

    response = client.post(
        f"/bookings/delete/{booking.id}", follow_redirects=False
    )
    workspace = client.get(f"/rooms/{room.id}")
    after = client.get(
        "/gantt/data?start=2026-09-01&end=2026-10-01"
    ).json()

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/rooms/{room.id}?success=booking_deleted"
    )
    assert "Visible antes de borrar" not in workspace.text
    assert after["properties"][0]["rooms"][0]["bookings"] == []


def test_booking_ui_hides_imported_delete_and_confirms_manual_delete():
    source = open("backend/static/js/bookings.js", encoding="utf-8").read()
    assert "readOnly || booking.editable === false" in source
    assert "externalBlockDeletable" in source
    assert '"Eliminar bloqueo"' in source
    assert "Esta acción no se puede deshacer" in source


def test_booking_ui_populates_room_and_resets_manual_imported_modes():
    source = open("backend/static/js/bookings.js", encoding="utf-8").read()
    workspace = open(
        "backend/templates/pages/room_workspace.html", encoding="utf-8"
    ).read()
    gantt = open("backend/templates/pages/gantt.html", encoding="utf-8").read()
    dashboard = open(
        "backend/templates/pages/dashboard.html", encoding="utf-8"
    ).read()

    assert "this.roomId.value = booking.room_id" in source
    assert source.count("this.resetModalState();") >= 2
    assert "this.roomId.disabled = false" in source
    assert 'this.form.action = "/bookings/create"' in source
    assert "this.importedGuestMode = false" in source
    assert "field.disabled = false" in source
    assert "field.disabled = readOnly" in source
    assert "/bookings/update-imported-local/" in source
    assert "booking.expected_arrival_date" in source
    assert "booking.expected_departure_date" in source
    assert "/bookings/update/" in source
    for template in (workspace, gantt, dashboard):
        assert "components/booking_modal.html" in template
        assert "js/bookings.js" in template


def test_booking_is_visible_when_every_request_uses_an_independent_session(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'independent_requests.db').as_posix()}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    setup_session = session_factory()
    try:
        room = create_room(setup_session)
        room_id = room.id
    finally:
        setup_session.close()

    app = create_app(initialize_database=False)

    def independent_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = independent_get_db
    try:
        with TestClient(app) as independent_client:
            create_response = independent_client.post(
                "/bookings/create",
                data=booking_data(room_id),
                follow_redirects=False,
            )
            list_response = independent_client.get(f"/bookings/room/{room_id}")
        assert create_response.status_code == 303
        assert create_response.headers["location"] == (
            f"/rooms/{room_id}?success=booking_created"
        )
        assert len(list_response.json()) == 1
        assert list_response.json()[0]["check_in"] == "2026-09-10"
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_booking_overlap_uses_error_redirect_and_keeps_original_contract(
    client, db_session
):
    room = create_room(db_session)
    first = client.post(
        "/bookings/create", data=booking_data(room.id), follow_redirects=False
    )
    overlap = client.post(
        "/bookings/create",
        data=booking_data(
            room.id, guest_name="Otra", check_in="2026-09-12", check_out="2026-09-20"
        ),
        follow_redirects=False,
    )
    assert first.status_code == 303
    assert overlap.status_code == 303
    assert overlap.headers["location"] == f"/rooms/{room.id}?error=booking_overlap"
    assert len(db_session.scalars(select(Booking)).all()) == 1


def test_update_uses_persisted_room_as_authority(client, db_session):
    first_room = create_room(db_session)
    second_property = Property(
        name="Piso Dos", address="Calle Dos", city="Elche",
        owner="HSI Rents", active=True,
    )
    db_session.add(second_property)
    db_session.flush()
    second_room = Room(
        property_id=second_property.id, code="H02", display_order=1,
        base_price=350, active=True,
    )
    db_session.add(second_room)
    db_session.commit()
    client.post("/bookings/create", data=booking_data(first_room.id))
    booking = db_session.scalar(select(Booking))

    response = client.post(
        f"/bookings/update/{booking.id}",
        data=booking_data(
            second_room.id, check_in="2026-10-01", check_out="2026-10-03"
        ),
        follow_redirects=False,
    )

    db_session.refresh(booking)
    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/rooms/{first_room.id}?success=booking_updated"
    )
    assert booking.room_id == first_room.id


def test_imported_booking_without_guest_returns_null_and_is_read_only(
    client, db_session
):
    room = create_room(db_session)
    platform = Platform(name="Booking.com", slug="booking", active=True)
    db_session.add(platform)
    db_session.flush()
    calendar = RoomCalendar(room_id=room.id, platform_id=platform.id, active=True)
    db_session.add(calendar)
    db_session.flush()
    booking = Booking(
        room_id=room.id,
        room_calendar_id=calendar.id,
        guest_id=None,
        origin="ical",
        check_in=date(2026, 11, 1),
        check_out=date(2026, 11, 5),
    )
    db_session.add(booking)
    db_session.commit()

    get_response = client.get(f"/bookings/{booking.id}")
    update_response = client.post(
        f"/bookings/update/{booking.id}",
        data=booking_data(
            room.id, guest_name="Ana", check_in="2026-11-02", check_out="2026-11-06"
        ),
        follow_redirects=False,
    )

    assert get_response.status_code == 200
    assert get_response.json()["guest_name"] is None
    assert get_response.json()["editable"] is False
    assert update_response.status_code == 303
    assert update_response.headers["location"] == (
        f"/rooms/{room.id}?error=booking_imported_read_only"
    )
    db_session.refresh(booking)
    assert booking.guest_id is None
    assert booking.check_in == date(2026, 11, 1)

    delete_response = client.post(
        f"/bookings/delete/{booking.id}", follow_redirects=False
    )
    assert delete_response.status_code == 303
    assert delete_response.headers["location"] == (
        f"/rooms/{room.id}?error=booking_imported_read_only"
    )
    assert db_session.get(Booking, booking.id) is not None


def test_imported_guest_endpoint_updates_only_guest_and_supports_empty_name(
    client, db_session
):
    room = create_room(db_session)
    platform = Platform(name="Spotahome", slug="spotahome", active=True)
    db_session.add(platform)
    db_session.flush()
    calendar = RoomCalendar(room_id=room.id, platform_id=platform.id, active=True)
    db_session.add(calendar)
    db_session.flush()
    booking = Booking(
        room_id=room.id, room_calendar_id=calendar.id, origin="spotahome",
        external_reference="spot-35", check_in=date(2026, 11, 1),
        check_out=date(2026, 11, 5), price=725,
    )
    db_session.add(booking)
    db_session.commit()
    original = (
        booking.room_id, booking.room_calendar_id, booking.origin,
        booking.external_reference, booking.check_in, booking.check_out,
        booking.price,
    )

    response = client.post(
        f"/bookings/update-imported-guest/{booking.id}",
        data={"guest_name": "  Nombre   Real  "}, follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/rooms/{room.id}?success=booking_guest_updated"
    )
    db_session.refresh(booking)
    assert booking.guest_id is None
    assert booking.source_guest_name == "Nombre Real"
    assert db_session.scalars(select(Person)).all() == []
    assert db_session.scalars(select(BookingParty)).all() == []
    assert (
        booking.room_id, booking.room_calendar_id, booking.origin,
        booking.external_reference, booking.check_in, booking.check_out,
        booking.price,
    ) == original
    assert "Nombre Real" in client.get(f"/rooms/{room.id}").text
    gantt = client.get(
        "/gantt/data?start=2026-11-01&end=2026-12-01"
    ).json()
    assert gantt["properties"][0]["rooms"][0]["bookings"][0]["guest_name"] == "Nombre Real"

    cleared = client.post(
        f"/bookings/update-imported-guest/{booking.id}",
        data={"guest_name": ""}, follow_redirects=False,
    )
    assert cleared.status_code == 303
    db_session.refresh(booking)
    assert booking.guest_id is None
    assert booking.source_guest_name is None


def test_imported_guest_endpoint_rejects_manual_booking(client, db_session):
    room = create_room(db_session)
    created = client.post(
        "/bookings/create",
        data=booking_data(room.id, guest_name="Manual"),
        follow_redirects=False,
    )
    assert created.status_code == 303
    booking = db_session.scalar(select(Booking).where(Booking.room_id == room.id))

    response = client.post(
        f"/bookings/update-imported-guest/{booking.id}",
        data={"guest_name": "Intruso"}, follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        f"/rooms/{room.id}?error=booking_not_imported"
    )
    db_session.refresh(booking)
    assert booking.parties[0].person.full_name == "Manual"
    assert booking.source_guest_name == "Manual"


def test_imported_local_details_update_only_guest_and_expected_dates(
    client, db_session
):
    room = create_room(db_session)
    platform = Platform(name="Flatio local", slug="flatio-local", active=True)
    db_session.add(platform)
    db_session.flush()
    calendar = RoomCalendar(
        room_id=room.id, platform_id=platform.id, active=True
    )
    db_session.add(calendar)
    db_session.flush()
    booking = Booking(
        room_id=room.id,
        room_calendar_id=calendar.id,
        origin=platform.slug,
        external_reference="LOCAL-DATES",
        check_in=date(2026, 9, 1),
        check_out=date(2027, 6, 30),
        price=725,
    )
    db_session.add(booking)
    db_session.commit()
    contractual = (
        booking.room_id,
        booking.room_calendar_id,
        booking.origin,
        booking.external_reference,
        booking.check_in,
        booking.check_out,
        booking.price,
    )

    response = client.post(
        f"/bookings/update-imported-local/{booking.id}",
        data={
            "guest_name": "Inquilino local",
            "expected_arrival_date": "2026-09-04",
            "expected_departure_date": "2027-06-28",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    db_session.refresh(booking)
    assert booking.guest_id is None
    assert booking.source_guest_name == "Inquilino local"
    assert booking.expected_arrival_date == date(2026, 9, 4)
    assert booking.expected_departure_date == date(2027, 6, 28)
    assert (
        booking.room_id,
        booking.room_calendar_id,
        booking.origin,
        booking.external_reference,
        booking.check_in,
        booking.check_out,
        booking.price,
    ) == contractual

    cleared = client.post(
        f"/bookings/update-imported-local/{booking.id}",
        data={"guest_name": "Inquilino local"},
        follow_redirects=False,
    )
    assert cleared.status_code == 303
    db_session.refresh(booking)
    assert booking.expected_arrival_date is None
    assert booking.expected_departure_date is None


def test_disappeared_housing_block_can_be_deleted_then_replaced_by_manual(
    client, db_session
):
    room = create_room(db_session)
    platform = Platform(
        name="HousingAnywhere", slug="housinganywhere", active=True,
        supports_import=True, supports_export=True,
    )
    db_session.add(platform)
    db_session.flush()
    sync_at = datetime(2026, 8, 19, 10, 0)
    calendar = RoomCalendar(
        room_id=room.id, platform_id=platform.id, active=True,
        feed_presence_tracking_started_at=sync_at, last_sync_at=sync_at,
    )
    db_session.add(calendar)
    db_session.flush()
    block = Booking(
        room_id=room.id, room_calendar_id=calendar.id,
        origin="housinganywhere", external_reference="BLOCK-GONE",
        notes="Manualmente bloqueado", check_in=date(2026, 11, 1),
        check_out=date(2026, 11, 5), last_seen_in_feed_at=None,
    )
    db_session.add(block)
    db_session.commit()

    detail = client.get(f"/bookings/{block.id}")
    deleted = client.post(
        f"/bookings/delete/{block.id}", follow_redirects=False
    )

    assert detail.json()["external_block_deletable"] is True
    assert deleted.status_code == 303
    assert deleted.headers["location"] == (
        f"/rooms/{room.id}?success=booking_external_block_deleted"
    )
    assert db_session.get(Booking, block.id) is None
    assert "BLOCK-GONE" not in client.get(f"/rooms/{room.id}").text
    gantt = client.get(
        "/gantt/data?start=2026-11-01&end=2026-12-01"
    ).json()
    assert gantt["properties"][0]["rooms"][0]["bookings"] == []

    created = client.post(
        "/bookings/create",
        data=booking_data(
            room.id, guest_name="Reconstruida",
            check_in="2026-11-01", check_out="2026-11-05",
        ),
        follow_redirects=False,
    )
    assert created.status_code == 303
    exported = client.get(
        f"/ical/rooms/{room.master_calendar_token}/{platform.slug}.ics"
    )
    events = [item for item in Calendar.from_ical(exported.content).walk()
              if item.name == "VEVENT"]
    assert len(events) == 1
    assert events[0].decoded("DTSTART") == date(2026, 11, 1)


def test_direct_delete_of_present_external_block_is_protected(client, db_session):
    room = create_room(db_session)
    platform = Platform(name="HousingAnywhere", slug="housinganywhere", active=True)
    db_session.add(platform)
    db_session.flush()
    sync_at = datetime(2026, 8, 19, 10, 0)
    calendar = RoomCalendar(
        room_id=room.id, platform_id=platform.id, active=True,
        feed_presence_tracking_started_at=sync_at, last_sync_at=sync_at,
    )
    db_session.add(calendar)
    db_session.flush()
    block = Booking(
        room_id=room.id, room_calendar_id=calendar.id,
        origin="housinganywhere", external_reference="BLOCK-PRESENT",
        notes="Manualmente bloqueado", check_in=date(2026, 11, 1),
        check_out=date(2026, 11, 5), last_seen_in_feed_at=sync_at,
    )
    db_session.add(block)
    db_session.commit()

    detail = client.get(f"/bookings/{block.id}")
    response = client.post(
        f"/bookings/delete/{block.id}", follow_redirects=False
    )

    assert detail.json()["external_block_deletable"] is False
    assert response.headers["location"] == (
        f"/rooms/{room.id}?error=booking_external_block_still_present"
    )
    assert db_session.get(Booking, block.id) is not None
