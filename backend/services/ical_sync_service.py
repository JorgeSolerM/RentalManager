from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.integrations.ical_event_filters import is_platform_calendar_echo
from backend.integrations.ical_http_client import IcalDownloadError, SafeIcalHttpClient
from backend.integrations.ical_guest_extractors import extract_guest_name
from backend.integrations.ical_parser import IcalParseError, IcalParser, NormalizedIcalEvent
from backend.models.booking import Booking
from backend.models.guest import Guest
from backend.repositories.booking_repository import BookingRepository
from backend.repositories.guest_repository import GuestRepository
from backend.repositories.room_calendar_repository import RoomCalendarRepository


@dataclass(frozen=True)
class IcalSyncReport:
    room_calendar_id: int
    received: int
    created: int
    updated: int
    unchanged: int
    cancelled: int
    disappeared: int
    ignored_echoes: int = 0

    @property
    def has_warnings(self) -> bool:
        return bool(self.cancelled or self.disappeared)


class IcalSyncService:
    def __init__(self, http_client=None, parser=None):
        self.http_client = http_client or SafeIcalHttpClient()
        self.parser = parser or IcalParser()
        self.booking_repository = BookingRepository()
        self.guest_repository = GuestRepository()
        self.calendar_repository = RoomCalendarRepository()

    def _get_or_create_guest(self, db: Session, full_name: str) -> Guest:
        normalized_name = full_name.strip()
        guest = self.guest_repository.get_by_full_name(db, normalized_name)
        if guest is None:
            guest = Guest(
                full_name=normalized_name,
                display_name=normalized_name,
                active=True,
            )
            self.guest_repository.create(db, guest)
        return guest

    @staticmethod
    def _overlaps(intervals: list[tuple[date, date]]) -> bool:
        ordered = sorted(intervals)
        return any(
            current_start < previous_end
            for (_, previous_end), (current_start, _) in zip(ordered, ordered[1:])
        )

    @staticmethod
    def _is_overlap_error(error: IntegrityError) -> bool:
        return "booking_overlap" in str(error.orig)

    def _validate_final_state(
        self,
        db: Session,
        room_id: int,
        calendar_id: int,
        active_events: dict[str, NormalizedIcalEvent],
    ) -> bool:
        intervals = []
        for booking in self.booking_repository.list_by_room(db, room_id):
            event = (
                active_events.get(booking.external_reference)
                if booking.room_calendar_id == calendar_id
                else None
            )
            if event is None:
                intervals.append((booking.check_in, booking.check_out))
            else:
                intervals.append((event.check_in, event.check_out))

        existing_references = {
            booking.external_reference
            for booking in self.booking_repository.list_by_room_calendar(db, calendar_id)
        }
        intervals.extend(
            (event.check_in, event.check_out)
            for uid, event in active_events.items()
            if uid not in existing_references
        )
        return not self._overlaps(intervals)

    def synchronize(
        self,
        db: Session,
        room_calendar_id: int,
    ) -> OperationResult[IcalSyncReport]:
        calendar = self.calendar_repository.get_by_id(db, room_calendar_id)
        if calendar is None:
            db.rollback()
            return OperationResult(success=False, message="not_found")
        if not calendar.active:
            db.rollback()
            return OperationResult(success=False, message="room_calendar_inactive")
        if not calendar.room.active:
            db.rollback()
            return OperationResult(success=False, message="room_calendar_room_inactive")
        if not calendar.platform.active:
            db.rollback()
            return OperationResult(success=False, message="room_calendar_platform_inactive")
        if not calendar.platform.supports_import or not calendar.import_url:
            db.rollback()
            return OperationResult(success=False, message="room_calendar_import_not_supported")

        try:
            content = self.http_client.download(calendar.import_url)
            events = self.parser.parse(content)
            sync_events = [
                event
                for event in events
                if not is_platform_calendar_echo(
                    calendar.platform.slug,
                    event,
                )
            ]
            ignored_echoes = len(events) - len(sync_events)
            active_events = {
                event.uid: event for event in sync_events if not event.cancelled
            }
            cancelled_uids = {
                event.uid for event in sync_events if event.cancelled
            }
            existing = self.booking_repository.list_by_room_calendar(db, calendar.id)
            existing_by_reference = {
                booking.external_reference: booking
                for booking in existing
                if booking.external_reference is not None
            }

            if not self._validate_final_state(
                db, calendar.room_id, calendar.id, active_events
            ):
                db.rollback()
                return OperationResult(success=False, message="room_calendar_sync_overlap")

            created = updated = unchanged = 0
            for uid, event in active_events.items():
                booking = existing_by_reference.get(uid)
                guest_name = extract_guest_name(
                    calendar.platform.slug,
                    event.summary,
                )
                if booking is None:
                    guest = (
                        self._get_or_create_guest(db, guest_name)
                        if guest_name is not None
                        else None
                    )
                    booking = Booking(
                        room_id=calendar.room_id,
                        room_calendar_id=calendar.id,
                        guest_id=guest.id if guest is not None else None,
                        origin=calendar.platform.slug,
                        external_reference=uid,
                        check_in=event.check_in,
                        check_out=event.check_out,
                        price=None,
                        notes=event.notes,
                    )
                    self.booking_repository.create(db, booking)
                    created += 1
                else:
                    changed = False
                    if (
                        booking.check_in != event.check_in
                        or booking.check_out != event.check_out
                    ):
                        booking.check_in = event.check_in
                        booking.check_out = event.check_out
                        booking.notes = event.notes
                        changed = True
                    if booking.guest_id is None and guest_name is not None:
                        guest = self._get_or_create_guest(db, guest_name)
                        booking.guest_id = guest.id
                        changed = True
                    if changed:
                        self.booking_repository.update(db, booking)
                        updated += 1
                    else:
                        unchanged += 1

            active_uids = set(active_events)
            disappeared = sum(
                1
                for booking in existing
                if booking.external_reference is not None
                and booking.external_reference not in active_uids
                and booking.external_reference not in cancelled_uids
            )
            cancelled = len(cancelled_uids)

            calendar.last_sync_at = datetime.now(timezone.utc).replace(tzinfo=None)
            self.calendar_repository.mark_synced(db, calendar)
            db.commit()
            report = IcalSyncReport(
                room_calendar_id=calendar.id,
                received=len(events),
                created=created,
                updated=updated,
                unchanged=unchanged,
                cancelled=cancelled,
                disappeared=disappeared,
                ignored_echoes=ignored_echoes,
            )
            message = (
                "room_calendar_sync_completed_with_warnings"
                if report.has_warnings
                else "room_calendar_sync_completed"
            )
            return OperationResult(success=True, message=message, data=report)
        except (IcalDownloadError, IcalParseError) as error:
            db.rollback()
            return OperationResult(success=False, message=error.code)
        except IntegrityError as error:
            db.rollback()
            if self._is_overlap_error(error):
                return OperationResult(success=False, message="room_calendar_sync_overlap")
            return OperationResult(success=False, message="room_calendar_sync_failed")
        except Exception:
            db.rollback()
            raise
