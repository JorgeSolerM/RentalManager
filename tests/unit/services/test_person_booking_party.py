from datetime import date

from sqlalchemy import select

from backend.models.booking import Booking
from backend.models.booking_party import BookingParty
from backend.models.person import Person
from backend.models.property import Property
from backend.models.room import Room
from backend.services.booking_party_service import BookingPartyService
from backend.services.person_service import PersonService
from backend.core.iban import format_iban, mask_iban


def make_booking(db):
    prop = Property(name="Personas", address="Calle", city="Elche", owner="HSI", active=True)
    db.add(prop); db.flush()
    room = Room(property_id=prop.id, code="P01", display_order=1, active=True)
    db.add(room); db.flush()
    booking = Booking(room_id=room.id, origin="manual", check_in=date(2026, 9, 1), check_out=date(2026, 10, 1))
    db.add(booking); db.commit(); return booking


def create_person(db, name="Persona", **values):
    return PersonService().save(db, None, full_name=name, active=True, **values).data


def test_person_can_be_incomplete_and_is_normalized(db_session):
    result = PersonService().save(db_session, None, full_name="  Ana   Pérez  ", email=" ANA@EXAMPLE.COM ", phone=" +34 600 123 123 ", active=True)
    assert result.success
    assert result.data.full_name == "Ana Pérez"
    assert result.data.email == "ana@example.com"
    assert result.data.document_number is None
    assert result.data.iban is None


def test_person_iban_accepts_international_values_and_normalizes_storage(db_session):
    spanish = create_person(db_session, "IBAN ES", iban="es91 2100 0418 4502 0005 1332")
    foreign = create_person(db_session, "IBAN GB", iban="GB82 WEST 1234 5698 7654 32")

    assert spanish.iban == "ES9121000418450200051332"
    assert foreign.iban == "GB82WEST12345698765432"
    assert format_iban(spanish.iban) == "ES91 2100 0418 4502 0005 1332"
    assert mask_iban(spanish.iban) == "ES•• •••• •••• •••• •••• 1332"


def test_person_iban_rejects_invalid_checksum_without_persisting_value(db_session):
    result = PersonService().save(
        db_session,
        None,
        full_name="IBAN incorrecto",
        iban="ES91 2100 0418 4502 0005 1333",
        active=True,
    )

    assert not result.success
    assert result.message == "person_iban_invalid"
    assert db_session.scalar(select(Person).where(Person.full_name == "IBAN incorrecto")) is None


def test_people_are_not_deduplicated_by_name(db_session):
    first = create_person(db_session, "Mismo Nombre")
    second = create_person(db_session, "Mismo Nombre")
    assert first.id != second.id


def test_multiple_people_and_roles_are_supported_without_exact_duplicates(db_session):
    booking = make_booking(db_session); first = create_person(db_session, "Primera"); second = create_person(db_session, "Segunda")
    service = BookingPartyService()
    assert service.add(db_session, booking.id, first.id, "tenant").success
    assert service.add(db_session, booking.id, first.id, "occupant").success
    assert service.add(db_session, booking.id, second.id, "tenant").success
    duplicate = service.add(db_session, booking.id, first.id, "tenant")
    assert not duplicate.success and duplicate.message == "booking_party_duplicate"
    assert len(db_session.scalars(select(BookingParty).where(BookingParty.booking_id == booking.id)).all()) == 3


def test_person_can_be_shared_roles_removed_and_linked_person_cannot_be_deleted(db_session):
    first_booking = make_booking(db_session); second_booking = make_booking(db_session); person = create_person(db_session)
    parties = BookingPartyService()
    first = parties.add(db_session, first_booking.id, person.id, "payer").data
    assert parties.add(db_session, second_booking.id, person.id, "guarantor").success
    assert PersonService().delete(db_session, person.id).message == "person_has_booking_parties"
    assert parties.remove(db_session, first.id, first_booking.id).success
    assert db_session.get(Person, person.id) is not None


def test_booking_delete_cascades_parties_but_preserves_person(db_session):
    booking = make_booking(db_session); person = create_person(db_session)
    BookingPartyService().add(db_session, booking.id, person.id, "unclassified")
    db_session.delete(booking); db_session.commit()
    assert db_session.scalar(select(BookingParty).where(BookingParty.booking_id == booking.id)) is None
    assert db_session.get(Person, person.id) is not None
