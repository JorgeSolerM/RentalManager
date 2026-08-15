from datetime import date

from sqlalchemy import select

from backend.models.booking import Booking
from backend.models.property import Property
from backend.models.room import Room


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
