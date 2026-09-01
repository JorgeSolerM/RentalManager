from datetime import date

from sqlalchemy import event, select

from backend.models.booking import Booking
from backend.models.booking_party import BookingParty
from backend.models.person import Person
from backend.models.room import Room
from tests.integration.api.test_bookings_routes import create_room


def test_person_create_edit_search_and_detail_allow_incomplete_record(client, db_session):
    created = client.post(
        "/persons/create",
        data={"full_name": "  Ana   Pérez  ", "active": "true"},
        follow_redirects=False,
    )
    person = db_session.scalar(select(Person))

    assert created.status_code == 303
    assert created.headers["location"] == f"/persons/{person.id}"
    assert person.full_name == "Ana Pérez"
    assert person.document_number is None
    assert client.get("/persons?q=ana").status_code == 200
    assert "Ana Pérez" in client.get("/persons?q=ana").text

    updated = client.post(
        f"/persons/{person.id}/update",
        data={
            "full_name": "Ana Pérez López",
            "email": "ANA@EXAMPLE.COM",
            "iban": "es91 2100 0418 4502 0005 1332",
            "document_type": "dni",
            "document_number": "123x",
            "nationality": "es",
            "verification_status": "verified",
            "active": "true",
        },
        follow_redirects=False,
    )
    db_session.refresh(person)
    assert updated.status_code == 303
    assert person.email == "ana@example.com"
    assert person.document_number == "123X"
    assert person.nationality == "ES"
    assert person.iban == "ES9121000418450200051332"
    detail = client.get(f"/persons/{person.id}")
    edit = client.get(f"/persons/{person.id}/edit")
    assert "Ana Pérez López" in detail.text
    assert "ES••" in detail.text and "1332" in detail.text
    assert "ES91 2100 0418 4502 0005 1332" in edit.text

    listing = client.get("/persons")
    assert "ES9121000418450200051332" not in listing.text
    assert "ES91 2100 0418 4502 0005 1332" not in listing.text


def test_person_invalid_iban_is_rejected_with_controlled_error(client, db_session):
    response = client.post(
        "/persons/create",
        data={
            "full_name": "IBAN inválido",
            "iban": "ES91 2100 0418 4502 0005 1333",
            "active": "true",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/persons/new?error=person_iban_invalid"
    assert "1333" not in response.headers["location"]
    assert db_session.scalar(select(Person)) is None


def test_booking_party_routes_add_multiple_roles_and_remove_one(client, db_session):
    room = create_room(db_session)
    person = Person(full_name="Persona compartida", active=True)
    booking = Booking(
        room_id=room.id,
        origin="manual",
        source_guest_name="Canal",
        check_in=date(2026, 9, 1),
        check_out=date(2026, 10, 1),
    )
    db_session.add_all([person, booking])
    db_session.commit()

    first = client.post(
        f"/bookings/{booking.id}/parties",
        data={"person_id": person.id, "role": "tenant"},
    )
    second = client.post(
        f"/bookings/{booking.id}/parties",
        data={"person_id": person.id, "role": "payer"},
    )
    duplicate = client.post(
        f"/bookings/{booking.id}/parties",
        data={"person_id": person.id, "role": "tenant"},
    )

    assert first.status_code == second.status_code == 200
    assert duplicate.status_code == 422
    assert {party.role for party in booking.parties} == {"tenant", "payer"}

    removed = client.post(
        f"/bookings/{booking.id}/parties/{first.json()['id']}/remove"
    )
    db_session.expire_all()
    assert removed.status_code == 200
    assert [party.role for party in db_session.scalars(select(BookingParty)).all()] == ["payer"]


def test_person_linked_to_booking_cannot_be_deleted(client, db_session):
    room = create_room(db_session)
    person = Person(full_name="Persona vinculada", active=True)
    booking = Booking(
        room_id=room.id,
        origin="manual",
        check_in=date(2026, 9, 1),
        check_out=date(2026, 10, 1),
    )
    db_session.add_all([person, booking])
    db_session.flush()
    db_session.add(BookingParty(booking_id=booking.id, person_id=person.id, role="occupant"))
    db_session.commit()

    response = client.post(f"/persons/{person.id}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert "error=person_has_booking_parties" in response.headers["location"]
    assert db_session.get(Person, person.id) is not None


def test_person_list_uses_name_navigation_status_and_delete_confirmation(
    client, db_session
):
    person = Person(full_name="Persona navegable", active=False)
    db_session.add(person)
    db_session.commit()

    response = client.get("/persons")

    assert response.status_code == 200
    assert f'href="/persons/{person.id}"' in response.text
    assert "Ver ficha" not in response.text
    assert f'action="/persons/{person.id}/delete"' in response.text
    assert "¿Eliminar este inquilino?" in response.text
    assert 'aria-label="Eliminar inquilino"' in response.text
    assert 'title="Eliminar"' in response.text
    assert ">Eliminar</button>" not in response.text
    assert "<h1 class=\"h3 mb-1\">Inquilinos</h1>" in response.text
    assert 'href="/persons/new">Nuevo inquilino</a>' in response.text
    assert 'for="personSearch">Buscar inquilinos</label>' in response.text
    assert 'aria-label="Inactiva"' in response.text
    assert "Sin propiedad" in response.text
    assert 'class="person-avatar-placeholder" aria-hidden="true">PN</span>' in response.text
    assert 'aria-sort="ascending"' in response.text


def test_person_without_booking_can_be_deleted_including_legacy(
    client, db_session
):
    person = Person(
        full_name="Legacy sin reserva",
        active=True,
        source="legacy_guest",
    )
    db_session.add(person)
    db_session.commit()
    person_id = person.id

    response = client.post(f"/persons/{person_id}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/persons?success=person_deleted"
    assert db_session.get(Person, person_id) is None


def test_person_list_summarizes_only_current_properties_without_n_plus_one(
    client, db_session, monkeypatch
):
    monkeypatch.setattr(
        "backend.api.routers.persons.business_today", lambda: date(2026, 9, 1)
    )
    first_room = create_room(db_session)
    second_room = create_room(db_session)
    first_room.property.name = "Alpha Property"
    second_room.property.name = "Zeta Property"
    first_property_sibling = Room(
        property_id=first_room.property_id,
        code="H02",
        display_order=2,
        base_price=350,
        active=True,
    )
    db_session.add(first_property_sibling)
    db_session.commit()
    one_property = Person(full_name="Una propiedad", active=True)
    many_properties = Person(full_name="Varias propiedades", active=True)
    historical = Person(full_name="Solo histórico", active=True)
    never_linked = Person(full_name="Nunca vinculada", active=True)
    db_session.add_all([one_property, many_properties, historical, never_linked])
    db_session.flush()
    bookings = [
        Booking(room_id=first_room.id, origin="manual", check_in=date(2026, 8, 1), check_out=date(2026, 10, 1)),
        Booking(room_id=first_property_sibling.id, origin="manual", check_in=date(2026, 8, 2), check_out=date(2026, 10, 2)),
        Booking(room_id=second_room.id, origin="manual", check_in=date(2026, 8, 3), check_out=date(2026, 10, 3)),
        Booking(room_id=first_room.id, origin="manual", check_in=date(2025, 1, 1), check_out=date(2025, 2, 1)),
    ]
    db_session.add_all(bookings)
    db_session.flush()
    db_session.add_all([
        BookingParty(booking_id=bookings[0].id, person_id=one_property.id, role="occupant"),
        BookingParty(booking_id=bookings[0].id, person_id=many_properties.id, role="occupant"),
        BookingParty(booking_id=bookings[1].id, person_id=many_properties.id, role="payer"),
        BookingParty(booking_id=bookings[2].id, person_id=many_properties.id, role="tenant"),
        BookingParty(booking_id=bookings[3].id, person_id=historical.id, role="unclassified"),
    ])
    db_session.commit()
    statements = []

    def count_selects(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(db_session.get_bind(), "before_cursor_execute", count_selects)
    try:
        response = client.get("/persons")
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", count_selects)

    assert response.status_code == 200
    assert first_room.property.name in response.text
    assert "2 propiedades" in response.text
    assert "Sin estancia actual" in response.text
    assert "Sin propiedad" in response.text
    assert len(statements) <= 5

    name_asc = client.get("/persons?sort=name&direction=asc").text
    name_desc = client.get("/persons?sort=name&direction=desc").text
    assert name_asc.index("Nunca vinculada") < name_asc.index("Solo histórico")
    assert name_desc.index("Solo histórico") < name_desc.index("Nunca vinculada")

    property_asc = client.get("/persons?sort=property&direction=asc").text
    property_desc = client.get("/persons?sort=property&direction=desc").text
    assert property_asc.index("Una propiedad") < property_asc.index("Varias propiedades")
    assert property_desc.index("Varias propiedades") < property_desc.index("Una propiedad")
    for rendered in (property_asc, property_desc):
        assert rendered.index("Una propiedad") < rendered.index("Solo histórico")
        assert rendered.index("Varias propiedades") < rendered.index("Solo histórico")
        assert rendered.index("Solo histórico") < rendered.index("Nunca vinculada")


def test_person_sort_is_stable_and_search_preserves_order_parameters(
    client, db_session
):
    first = Person(full_name="Nombre repetido", active=True)
    second = Person(full_name="Nombre repetido", active=True)
    db_session.add_all([first, second])
    db_session.commit()

    ascending = client.get(
        "/persons?q=Nombre&sort=name&direction=asc"
    )
    descending = client.get(
        "/persons?q=Nombre&sort=name&direction=desc"
    )

    assert ascending.status_code == descending.status_code == 200
    for response in (ascending, descending):
        assert response.text.index(f'/persons/{first.id}') < response.text.index(
            f'/persons/{second.id}'
        )
        assert 'name="sort" value="name"' in response.text
        assert 'name="direction" value="' in response.text
        assert "q=Nombre&amp;sort=property" in response.text
