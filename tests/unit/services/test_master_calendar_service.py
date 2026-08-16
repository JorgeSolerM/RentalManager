from datetime import date

from icalendar import Calendar

from backend.models.booking import Booking
from backend.models.platform import Platform
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar
from backend.services.master_calendar_service import MasterCalendarService


def seed_export_data(db_session):
    property_obj = Property(name="Export Test", address="Private address", city="Madrid", owner="Private owner", active=True)
    db_session.add(property_obj)
    db_session.flush()
    room = Room(property_id=property_obj.id, code="SECRET-ROOM", display_order=1, base_price=999, active=True)
    housing = Platform(name="HousingAnywhere", slug="housinganywhere", active=True, supports_import=True, supports_export=True)
    flatio = Platform(name="Flatio", slug="flatio", active=True, supports_import=True, supports_export=True)
    inactive = Platform(name="Inactive", slug="inactive", active=False, supports_import=False, supports_export=True)
    unsupported = Platform(name="Import only", slug="import-only", active=True, supports_import=True, supports_export=False)
    db_session.add_all([room, housing, flatio, inactive, unsupported])
    db_session.flush()
    housing_calendar = RoomCalendar(room_id=room.id, platform_id=housing.id, import_url="https://example.com/housing.ics", active=True)
    flatio_calendar = RoomCalendar(room_id=room.id, platform_id=flatio.id, import_url="https://example.com/flatio.ics", active=True)
    db_session.add_all([housing_calendar, flatio_calendar])
    db_session.flush()
    bookings = [
        Booking(room_id=room.id, room_calendar_id=housing_calendar.id, origin="housinganywhere", external_reference="HA-SECRET", check_in=date(2026, 5, 8), check_out=date(2026, 8, 31), price=900, notes="Housing private notes"),
        Booking(room_id=room.id, room_calendar_id=flatio_calendar.id, origin="flatio", external_reference="FL-SECRET", check_in=date(2026, 10, 1), check_out=date(2027, 2, 28), price=800, notes="Flatio private notes"),
        Booking(room_id=room.id, origin="manual", check_in=date(2028, 2, 1), check_out=date(2028, 2, 29), price=700, notes="Manual private notes"),
    ]
    db_session.add_all(bookings)
    db_session.commit()
    return room, housing, flatio, inactive, unsupported, bookings


def parsed_events(export):
    calendar = Calendar.from_ical(export.content)
    return [component for component in calendar.walk() if component.name == "VEVENT"]


def test_platform_views_exclude_only_the_consuming_platform(db_session):
    room, housing, flatio, _, _, bookings = seed_export_data(db_session)
    service = MasterCalendarService()
    housing_export = service.export_for_platform(db_session, room.master_calendar_token, housing.slug)
    flatio_export = service.export_for_platform(db_session, room.master_calendar_token, flatio.slug)
    housing_uids = {str(event["UID"]) for event in parsed_events(housing_export)}
    flatio_uids = {str(event["UID"]) for event in parsed_events(flatio_export)}
    assert housing_uids == {f"{bookings[1].ical_uid}@rentalmanager", f"{bookings[2].ical_uid}@rentalmanager"}
    assert flatio_uids == {f"{bookings[0].ical_uid}@rentalmanager", f"{bookings[2].ical_uid}@rentalmanager"}


def test_export_dates_rfc_fields_and_privacy(db_session):
    room, housing, _, _, _, bookings = seed_export_data(db_session)
    export = MasterCalendarService().export_for_platform(db_session, room.master_calendar_token, housing.slug)
    by_uid = {str(event["UID"]): event for event in parsed_events(export)}
    flatio = by_uid[f"{bookings[1].ical_uid}@rentalmanager"]
    leap_year = by_uid[f"{bookings[2].ical_uid}@rentalmanager"]
    assert flatio.decoded("DTSTART") == date(2026, 10, 1)
    assert flatio.decoded("DTEND") == date(2027, 3, 1)
    assert leap_year.decoded("DTSTART") == date(2028, 2, 1)
    assert leap_year.decoded("DTEND") == date(2028, 3, 1)
    assert set(flatio.keys()) == {"UID", "DTSTAMP", "DTSTART", "DTEND", "SUMMARY", "STATUS", "TRANSP"}
    assert str(flatio["SUMMARY"]) == "Reserved"
    assert str(flatio["STATUS"]) == "CONFIRMED"
    assert str(flatio["TRANSP"]) == "OPAQUE"
    payload = export.content.decode("utf-8").lower()
    for secret in ("SECRET-ROOM", "Private address", "Private owner", "HA-SECRET", "FL-SECRET", "private notes", "housinganywhere", "flatio", "999"):
        assert secret.lower() not in payload


def test_inactive_room_exports_but_invalid_platform_views_do_not(db_session):
    room, housing, _, inactive, unsupported, _ = seed_export_data(db_session)
    room.active = False
    db_session.commit()
    service = MasterCalendarService()
    assert service.export_for_platform(db_session, room.master_calendar_token, housing.slug) is not None
    assert service.export_for_platform(db_session, room.master_calendar_token, inactive.slug) is None
    assert service.export_for_platform(db_session, room.master_calendar_token, unsupported.slug) is None
    assert service.export_for_platform(db_session, "invalid", housing.slug) is None


def test_regeneration_revokes_token_without_changing_booking_uids(db_session):
    room, housing, _, _, _, bookings = seed_export_data(db_session)
    service = MasterCalendarService()
    old_token = room.master_calendar_token
    old_uids = [booking.ical_uid for booking in bookings]
    result = service.regenerate_token(db_session, room.id)
    assert result.success
    assert result.data.master_calendar_token != old_token
    assert service.export_for_platform(db_session, old_token, housing.slug) is None
    assert [booking.ical_uid for booking in bookings] == old_uids


def test_public_views_require_explicit_base_url(db_session, monkeypatch):
    room, housing, flatio, _, _, _ = seed_export_data(db_session)
    service = MasterCalendarService()
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    assert {view["url"] for view in service.list_public_views(db_session, room)} == {None}
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://rental.example/")
    views = service.list_public_views(db_session, room)
    assert {view["platform"].id for view in views} == {housing.id, flatio.id}
    assert all(view["url"].startswith("https://rental.example/ical/rooms/") for view in views)


def test_empty_calendar_is_valid_and_etag_tracks_occupancy(db_session):
    room, housing, _, _, _, bookings = seed_export_data(db_session)
    for booking in bookings:
        db_session.delete(booking)
    db_session.commit()
    service = MasterCalendarService()
    empty = service.export_for_platform(db_session, room.master_calendar_token, housing.slug)
    assert parsed_events(empty) == []

    booking = Booking(
        room_id=room.id, origin="manual",
        check_in=date(2029, 1, 1), check_out=date(2029, 1, 2),
    )
    db_session.add(booking)
    db_session.commit()
    occupied = service.export_for_platform(db_session, room.master_calendar_token, housing.slug)
    assert occupied.etag != empty.etag
    assert len(parsed_events(occupied)) == 1
