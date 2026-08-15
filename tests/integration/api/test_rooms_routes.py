from sqlalchemy import select

from backend.models.property import Property
from backend.models.room import Room


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
