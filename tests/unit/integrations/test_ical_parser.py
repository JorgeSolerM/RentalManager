from datetime import date

import pytest

from backend.integrations.ical_parser import IcalParseError, IcalParser, MAX_EVENTS


def calendar(*events):
    body = "\r\n".join(events)
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\n{body}\r\nEND:VCALENDAR\r\n".encode()


def event(uid="UID-1", extra="DTSTART;VALUE=DATE:20260901\r\nDTEND;VALUE=DATE:20260905"):
    return f"BEGIN:VEVENT\r\nUID:{uid}\r\n{extra}\r\nEND:VEVENT"


def test_all_day_dtend_is_exclusive_and_missing_dtend_means_one_day():
    parsed = IcalParser().parse(calendar(
        event("WITH-END"),
        event("ONE-DAY", "DTSTART;VALUE=DATE:20261010"),
    ))
    assert (parsed[0].check_in, parsed[0].check_out) == (
        date(2026, 9, 1), date(2026, 9, 5)
    )
    assert (parsed[1].check_in, parsed[1].check_out) == (
        date(2026, 10, 10), date(2026, 10, 11)
    )


def test_timed_events_are_converted_to_europe_madrid_before_dates():
    parsed = IcalParser().parse(calendar(event(
        extra="DTSTART:20260901T223000Z\r\nDTEND:20260902T223000Z"
    )))[0]
    assert parsed.check_in == date(2026, 9, 2)
    assert parsed.check_out == date(2026, 9, 3)


def test_summary_and_description_are_plain_bounded_notes():
    parsed = IcalParser().parse(calendar(event(
        extra="DTSTART;VALUE=DATE:20260901\r\nDTEND;VALUE=DATE:20260902\r\nSUMMARY:<b>Guest</b>\r\nDESCRIPTION:External text"
    )))[0]
    assert parsed.notes == "<b>Guest</b>\n\nExternal text"


@pytest.mark.parametrize(
    "bad_event",
    [
        event("", "DTSTART;VALUE=DATE:20260901"),
        event("NO-START", "DTEND;VALUE=DATE:20260902"),
        event("INVERTED", "DTSTART;VALUE=DATE:20260902\r\nDTEND;VALUE=DATE:20260901"),
        event("TIMED-NO-END", "DTSTART:20260901T120000Z"),
    ],
)
def test_invalid_events_reject_whole_feed(bad_event):
    with pytest.raises(IcalParseError):
        IcalParser().parse(calendar(event("VALID"), bad_event))


@pytest.mark.parametrize("property_line", ["RRULE:FREQ=DAILY", "RDATE:20260903", "EXDATE:20260903", "RECURRENCE-ID:20260901"])
def test_recurrence_properties_are_rejected(property_line):
    with pytest.raises(IcalParseError, match="recurrence_not_supported"):
        IcalParser().parse(calendar(event(extra=(
            "DTSTART;VALUE=DATE:20260901\r\nDTEND;VALUE=DATE:20260902\r\n" + property_line
        ))))


def test_cancelled_event_only_requires_uid_and_does_not_produce_dates():
    parsed = IcalParser().parse(calendar(event("CANCELLED-1", "STATUS:CANCELLED")))[0]
    assert parsed.cancelled
    assert parsed.check_in is None and parsed.check_out is None


def test_duplicate_or_excessive_events_are_rejected():
    with pytest.raises(IcalParseError):
        IcalParser().parse(calendar(event("DUP"), event("DUP")))
    many = calendar(*(event(f"UID-{index}") for index in range(MAX_EVENTS + 1)))
    with pytest.raises(IcalParseError, match="too_many_events"):
        IcalParser().parse(many)


def test_uid_is_stripped_and_must_fit_database_identity_column():
    parsed = IcalParser().parse(calendar(event("  Mixed-Case-UID  ")))[0]
    assert parsed.uid == "Mixed-Case-UID"
    with pytest.raises(IcalParseError):
        IcalParser().parse(calendar(event("X" * 256)))
