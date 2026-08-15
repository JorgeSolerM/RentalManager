from datetime import date

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from backend.app_factory import create_app
from backend.database.base import Base
from backend.database.session import get_db
from backend.models.booking import Booking
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar


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
    assert booking.guest.full_name == "Ana Pérez"
    assert booking.check_in == date(2026, 9, 10)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert get_response.status_code == 200
    assert get_response.json() == {
        "id": booking.id,
        "room_id": room.id,
        "guest_name": "Ana Pérez",
        "origin": "manual",
        "check_in": "2026-09-10",
        "check_out": "2026-09-15",
        "price": 450.5,
        "notes": "Reserva de prueba",
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
        ),
        follow_redirects=False,
    )
    db_session.refresh(booking)
    assert booking.guest.full_name == "Luis García"
    assert booking.check_in == date(2026, 10, 1)

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
        f"/rooms/{room.id}?error=booking_delete_not_allowed"
    )
    assert db_session.get(Booking, booking.id) is not None
    assert not_found_response.status_code == 404
    assert not_found_response.json() == {"detail": "Reserva no encontrada."}


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
    assert update_response.status_code == 303
    assert update_response.headers["location"] == (
        f"/rooms/{room.id}?error=booking_imported_read_only"
    )
    db_session.refresh(booking)
    assert booking.guest_id is None
    assert booking.check_in == date(2026, 11, 1)
