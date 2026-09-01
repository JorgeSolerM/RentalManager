from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from backend.core.business_time import business_today
from backend.core.booking_overlap import intervals_overlap, is_operational_overlap
from backend.repositories.gantt_repository import GanttRepository
from backend.core.booking_person_name import booking_person_name
from backend.schemas.gantt_schema import (
    GanttBooking,
    GanttData,
    GanttOrigin,
    GanttProperty,
    GanttRoom,
    GanttSyncPlatform,
    GanttSyncState,
    GanttWindow,
)
from backend.services.room_calendar_sync_runner import RoomCalendarSyncRunner


MAX_WINDOW_DAYS = 366


class GanttValidationError(ValueError):
    pass


class GanttService:
    def __init__(self, repository=None, sync_runner=None):
        self.repository = repository or GanttRepository()
        self.sync_runner = sync_runner or RoomCalendarSyncRunner()

    @staticmethod
    def default_window(
        today: date | None = None, months: int = 8
    ) -> tuple[date, date]:
        if months not in {4, 8, 12}:
            raise GanttValidationError("gantt_invalid_scale")
        today = today or business_today()
        start_month = today.month - 1
        start_year = today.year
        if start_month == 0:
            start_month = 12
            start_year -= 1
        start = date(start_year, start_month, 1)
        end_month_index = (start.year * 12 + start.month - 1) + months
        end = date(end_month_index // 12, end_month_index % 12 + 1, 1)
        return start, end

    @staticmethod
    def validate_window(start: date, end: date) -> None:
        if end <= start:
            raise GanttValidationError("gantt_invalid_window")
        if (end - start).days > MAX_WINDOW_DAYS:
            raise GanttValidationError("gantt_window_too_large")

    @staticmethod
    def _assign_lanes(bookings, today: date):
        lane_ends: list[date] = []
        assigned = []
        for booking in bookings:
            lane = next(
                (index for index, lane_end in enumerate(lane_ends) if lane_end <= booking.check_in),
                len(lane_ends),
            )
            if lane == len(lane_ends):
                lane_ends.append(booking.check_out)
            else:
                lane_ends[lane] = booking.check_out
            assigned.append((booking, lane))

        for booking, lane in assigned:
            conflicts = [
                other
                for other, _ in assigned
                if other.id != booking.id
                and intervals_overlap(
                    booking.check_in,
                    booking.check_out,
                    other.check_in,
                    other.check_out,
                )
            ]
            overlap_kind = None
            if conflicts:
                overlap_kind = (
                    "operational"
                    if any(
                        is_operational_overlap(
                            booking.check_in,
                            booking.check_out,
                            other.check_in,
                            other.check_out,
                            today,
                        )
                        for other in conflicts
                    )
                    else "historical"
                )
            yield booking, lane, overlap_kind

    def _sync_state(self, calendars) -> GanttSyncState:
        platforms = []
        severities = []
        for calendar in calendars:
            if not calendar.active or not calendar.import_url:
                continue
            if not calendar.automatic_sync_enabled:
                state = "paused"
            elif calendar.last_sync_status == "error":
                state = "error"
            elif self.sync_runner.is_overdue(calendar):
                state = "overdue"
            else:
                state = "ok"
            severities.append(state)
            platforms.append(
                GanttSyncPlatform(
                    slug=calendar.platform.slug,
                    name=calendar.platform.name,
                    state=state,
                )
            )
        priority = ("error", "overdue", "paused", "ok")
        severity = next((item for item in priority if item in severities), "none")
        return GanttSyncState(severity=severity, platforms=platforms)

    def get_data(
        self,
        db: Session,
        start: date,
        end: date,
        property_id: int | None = None,
        include_inactive: bool = False,
    ) -> GanttData:
        self.validate_window(start, end)
        today = business_today()
        rooms = self.repository.list_rooms(db, property_id, include_inactive)
        room_ids = [room.id for room in rooms]
        bookings = self.repository.list_bookings(db, room_ids, start, end)
        calendars = self.repository.list_room_calendars(db, room_ids)
        by_room_bookings = defaultdict(list)
        by_room_calendars = defaultdict(list)
        for booking in bookings:
            by_room_bookings[booking.room_id].append(booking)
        for calendar in calendars:
            by_room_calendars[calendar.room_id].append(calendar)

        property_map = {}
        for room in rooms:
            item = property_map.setdefault(
                room.property_id,
                GanttProperty(id=room.property.id, name=room.property.name, rooms=[]),
            )
            room_bookings = []
            for booking, lane, overlap_kind in self._assign_lanes(
                by_room_bookings[room.id], today
            ):
                platform = (
                    booking.room_calendar.platform
                    if booking.room_calendar is not None
                    else None
                )
                slug = platform.slug if platform else (booking.origin or "manual")
                name = platform.name if platform else (
                    "Manual" if slug == "manual" else slug.replace("-", " ").title()
                )
                room_bookings.append(
                    GanttBooking(
                        id=booking.id,
                        check_in=booking.check_in,
                        check_out=booking.check_out,
                        guest_name=booking_person_name(booking),
                        origin=GanttOrigin(
                            slug=slug,
                            name=name,
                            favicon=platform.favicon if platform else None,
                            color_key=slug,
                        ),
                        editable=booking.room_calendar_id is None,
                        historical=booking.check_out < today,
                        overlap_kind=overlap_kind,
                        lane=lane,
                    )
                )
            item.rooms.append(
                GanttRoom(
                    id=room.id,
                    code=room.code,
                    active=room.active,
                    sync=self._sync_state(by_room_calendars[room.id]),
                    bookings=room_bookings,
                )
            )
        return GanttData(
            window=GanttWindow(
                start=start,
                end=end,
                today=today,
                day_count=(end - start).days,
            ),
            properties=list(property_map.values()),
        )
