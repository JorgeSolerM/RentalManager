from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from icalendar import Calendar


BUSINESS_TIMEZONE = ZoneInfo("Europe/Madrid")
MAX_EVENTS = 2000
MAX_UID_LENGTH = 255
MAX_NOTES_LENGTH = 4000
RECURRENCE_PROPERTIES = {"RRULE", "RDATE", "EXDATE", "RECURRENCE-ID"}


class IcalParseError(Exception):
    def __init__(self, code: str = "room_calendar_sync_invalid_feed"):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class NormalizedIcalEvent:
    uid: str
    check_in: date | None
    check_out: date | None
    notes: str | None
    cancelled: bool


class IcalParser:
    @staticmethod
    def _decoded(component, name: str):
        try:
            return component.decoded(name)
        except (KeyError, ValueError, TypeError) as error:
            raise IcalParseError() from error

    @staticmethod
    def _to_business_date(value: date | datetime) -> date:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=BUSINESS_TIMEZONE)
            else:
                value = value.astimezone(BUSINESS_TIMEZONE)
            return value.date()
        if isinstance(value, date):
            return value
        raise IcalParseError()

    @staticmethod
    def _notes(component) -> str | None:
        values = []
        for name in ("SUMMARY", "DESCRIPTION"):
            value = component.get(name)
            if value is not None:
                text = str(value).strip()
                if text:
                    values.append(text)
        notes = "\n\n".join(values)[:MAX_NOTES_LENGTH]
        return notes or None

    def parse(self, content: bytes) -> list[NormalizedIcalEvent]:
        try:
            calendar = Calendar.from_ical(content)
        except Exception as error:
            raise IcalParseError() from error

        components = [component for component in calendar.walk() if component.name == "VEVENT"]
        if len(components) > MAX_EVENTS:
            raise IcalParseError("room_calendar_sync_too_many_events")

        seen_uids: set[str] = set()
        events = []
        for component in components:
            if any(component.get(name) is not None for name in RECURRENCE_PROPERTIES):
                raise IcalParseError("room_calendar_sync_recurrence_not_supported")

            uid = str(component.get("UID", "")).strip()
            if not uid or len(uid) > MAX_UID_LENGTH or uid in seen_uids:
                raise IcalParseError()
            seen_uids.add(uid)

            cancelled = str(component.get("STATUS", "")).strip().upper() == "CANCELLED"
            if cancelled:
                events.append(NormalizedIcalEvent(uid, None, None, None, True))
                continue

            start_value = self._decoded(component, "DTSTART")
            check_in = self._to_business_date(start_value)
            if component.get("DTEND") is None:
                if isinstance(start_value, datetime):
                    raise IcalParseError()
                check_out = check_in + timedelta(days=1)
            else:
                check_out = self._to_business_date(self._decoded(component, "DTEND"))
            if check_out <= check_in:
                raise IcalParseError()

            events.append(NormalizedIcalEvent(uid, check_in, check_out, self._notes(component), False))
        return events
