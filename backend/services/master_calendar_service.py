from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from icalendar import Calendar, Event
from sqlalchemy.orm import Session

from backend.core.config import get_public_base_url
from backend.core.operation_result import OperationResult
from backend.models.platform import Platform
from backend.models.room import Room
from backend.repositories.booking_repository import BookingRepository
from backend.repositories.platform_repository import PlatformRepository
from backend.repositories.room_repository import RoomRepository


@dataclass(frozen=True)
class CalendarExport:
    content: bytes
    etag: str
    room_id: int
    platform_id: int


class MasterCalendarService:
    def __init__(self):
        self.room_repository = RoomRepository()
        self.platform_repository = PlatformRepository()
        self.booking_repository = BookingRepository()

    def list_public_views(self, db: Session, room: Room) -> list[dict]:
        base_url = get_public_base_url()
        return [
            {
                "platform": platform,
                "url": (
                    f"{base_url}/ical/rooms/{room.master_calendar_token}/"
                    f"{platform.slug}.ics"
                    if base_url
                    else None
                ),
            }
            for platform in self.platform_repository.list_active_export_targets(db)
        ]

    def regenerate_token(
        self,
        db: Session,
        room_id: int,
    ) -> OperationResult[Room]:
        room = self.room_repository.get_by_id(db, room_id)
        if room is None:
            return OperationResult(success=False, message="not_found")
        try:
            room.master_calendar_token = secrets.token_urlsafe(32)
            self.room_repository.update(db, room)
            db.commit()
            return OperationResult(success=True, data=room)
        except Exception:
            db.rollback()
            raise

    def export_for_platform(
        self,
        db: Session,
        token: str,
        platform_slug: str,
    ) -> CalendarExport | None:
        room = self.room_repository.get_by_master_calendar_token(db, token)
        platform = self.platform_repository.get_by_slug(db, platform_slug)
        if (
            room is None
            or platform is None
            or not platform.active
            or not platform.supports_export
        ):
            return None

        bookings = [
            booking
            for booking in self.booking_repository.list_for_master_calendar(db, room.id)
            if not self._belongs_to_platform(booking, platform)
        ]
        etag = self._etag(platform.slug, bookings)
        calendar = Calendar()
        calendar.add("prodid", "-//RentalManager//Master Room Calendar//ES")
        calendar.add("version", "2.0")
        calendar.add("calscale", "GREGORIAN")
        calendar.add("method", "PUBLISH")
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)

        for booking in bookings:
            event = Event()
            event.add("uid", f"{booking.ical_uid}@rentalmanager")
            event.add("dtstamp", timestamp)
            event.add("dtstart", booking.check_in)
            event.add("dtend", booking.check_out + timedelta(days=1))
            event.add("summary", "Reserved")
            event.add("status", "CONFIRMED")
            event.add("transp", "OPAQUE")
            calendar.add_component(event)

        return CalendarExport(
            content=calendar.to_ical(),
            etag=etag,
            room_id=room.id,
            platform_id=platform.id,
        )

    @staticmethod
    def _belongs_to_platform(booking, platform: Platform) -> bool:
        return (
            booking.room_calendar is not None
            and booking.room_calendar.platform_id == platform.id
        )

    @staticmethod
    def _etag(platform_slug: str, bookings: list) -> str:
        state = "|".join(
            f"{booking.ical_uid}:{booking.check_in.isoformat()}:{booking.check_out.isoformat()}"
            for booking in bookings
        )
        digest = hashlib.sha256(f"{platform_slug}|{state}".encode()).hexdigest()
        return f'W/"{digest}"'
