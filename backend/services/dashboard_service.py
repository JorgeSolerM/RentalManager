from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.core.business_time import business_today
from backend.core.master_calendar_observation import master_calendar_evidence
from backend.core.platform_favicons import platform_favicon
from backend.repositories.dashboard_repository import DashboardRepository
from backend.schemas.dashboard_schema import (
    DashboardAvailability,
    DashboardData,
    DashboardIncident,
    DashboardMovement,
    DashboardPlatformSummary,
    DashboardSummary,
)
from backend.services.room_calendar_sync_runner import RoomCalendarSyncRunner


MOVEMENT_DAYS = 14
AVAILABILITY_DAYS = 30
INCIDENT_PRIORITY = {"critical": 0, "attention": 1, "informational": 2}


class DashboardService:
    def __init__(self, repository=None, sync_runner=None, now_factory=None):
        self.repository = repository or DashboardRepository()
        self.sync_runner = sync_runner or RoomCalendarSyncRunner()
        self.now_factory = now_factory or (
            lambda: datetime.now(timezone.utc).replace(tzinfo=None)
        )

    @staticmethod
    def _origin(booking) -> tuple[str, str, str | None]:
        platform = (
            booking.room_calendar.platform
            if booking.room_calendar is not None
            else None
        )
        slug = platform.slug if platform else (booking.origin or "manual")
        name = platform.name if platform else (
            "Manual" if slug == "manual" else slug.replace("-", " ").title()
        )
        favicon = platform_favicon(slug, platform.favicon if platform else None)
        return slug, name, favicon

    def _movement(
        self, booking, movement_date: date, today: date
    ) -> DashboardMovement:
        slug, name, favicon = self._origin(booking)
        return DashboardMovement(
            booking_id=booking.id,
            room_id=booking.room_id,
            room_code=booking.room.code,
            room_display_order=booking.room.display_order,
            property_name=booking.room.property.name,
            date=movement_date,
            days_remaining=max(0, (movement_date - today).days),
            guest_name=(booking.guest.full_name if booking.guest else "Huésped desconocido"),
            origin_name=name,
            origin_slug=slug,
            favicon=favicon,
            imported=booking.room_calendar_id is not None,
        )

    @staticmethod
    def _availability(rooms, bookings, today, availability_end):
        by_room = defaultdict(list)
        for booking in bookings:
            if booking.check_out > today:
                by_room[booking.room_id].append(
                    (booking.check_in, booking.check_out)
                )
        result = []
        for room in rooms:
            intervals = sorted(by_room[room.id])
            merged = []
            for start, end in intervals:
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))
            current_index = next(
                (
                    index for index, (start, end) in enumerate(merged)
                    if start <= today < end
                ),
                None,
            )
            if current_index is None:
                continue
            available_from = merged[current_index][1]
            if available_from > availability_end:
                continue
            next_interval = (
                merged[current_index + 1]
                if current_index + 1 < len(merged)
                else None
            )
            available_until = next_interval[0] if next_interval else None
            if available_until is not None and available_until <= available_from:
                continue
            result.append(DashboardAvailability(
                room_id=room.id,
                room_code=room.code,
                property_name=room.property.name,
                available_from=available_from,
                available_until=available_until,
            ))
        return sorted(
            result,
            key=lambda item: (item.available_from, item.property_name, item.room_code),
        )[:8]

    def get_dashboard(self, db: Session, today: date | None = None) -> DashboardData:
        today = today or business_today()
        movement_end = today + timedelta(days=MOVEMENT_DAYS)
        availability_end = today + timedelta(days=AVAILABILITY_DAYS)
        now = self.now_factory()

        rooms = self.repository.list_operational_rooms(db)
        bookings = self.repository.list_operational_bookings(
            db, today, availability_end, movement_end
        )
        calendars = self.repository.list_room_calendars(db)
        overlaps = self.repository.list_operational_overlaps(db, today)

        operational_room_ids = {room.id for room in rooms}
        occupied_room_ids = {
            booking.room_id
            for booking in bookings
            if (
                booking.room_id in operational_room_ids
                and booking.check_in <= today < booking.check_out
            )
        }
        arrivals = [
            self._movement(booking, booking.effective_arrival_date, today)
            for booking in bookings
            if today <= booking.effective_arrival_date <= movement_end
        ]
        departures = [
            self._movement(booking, booking.effective_departure_date, today)
            for booking in bookings
            if today <= booking.effective_departure_date <= movement_end
        ]
        movement_key = lambda item: (
            item.date, item.property_name, item.room_display_order,
            item.room_code, item.booking_id
        )
        arrivals.sort(key=movement_key)
        departures.sort(key=movement_key)

        incidents = []
        for overlap in overlaps:
            overlap_start = max(
                overlap["first_check_in"], overlap["second_check_in"]
            )
            overlap_end = min(
                overlap["first_check_out"], overlap["second_check_out"]
            )
            incidents.append(DashboardIncident(
                key=f"overlap:{overlap['first_booking_id']}:{overlap['second_booking_id']}",
                kind="operational_overlap",
                severity="critical",
                title="Solapamiento operativo",
                detail=(
                    f"{overlap['room_code']}: {overlap_start.strftime('%d/%m/%Y')}–"
                    f"{overlap_end.strftime('%d/%m/%Y')}"
                ),
                room_id=overlap["room_id"],
                room_code=overlap["room_code"],
                target_url="/gantt/",
            ))

        platform_counts = defaultdict(lambda: {"correct": 0, "review": 0, "platform": None})
        reliable_sync_times = []
        for calendar in calendars:
            if not calendar.active or not calendar.import_url:
                continue
            state = self.sync_runner.health_state(calendar, now=now)
            platform_entry = platform_counts[calendar.platform.slug]
            platform_entry["platform"] = calendar.platform
            if state == "ok":
                platform_entry["correct"] += 1
                if calendar.last_sync_at is not None:
                    reliable_sync_times.append(calendar.last_sync_at)
            else:
                platform_entry["review"] += 1

            target = f"/rooms/{calendar.room_id}#configuracion"
            if state == "error":
                incidents.append(DashboardIncident(
                    key=f"calendar-error:{calendar.id}", kind="calendar_error",
                    severity="critical", title="Error de sincronización",
                    detail=f"{calendar.room.code} · {calendar.platform.name}",
                    room_id=calendar.room_id, room_code=calendar.room.code,
                    platform_name=calendar.platform.name, target_url=target,
                ))
            elif state == "paused":
                incidents.append(DashboardIncident(
                    key=f"calendar-paused:{calendar.id}", kind="calendar_paused",
                    severity="attention", title="Automatización pausada",
                    detail=f"{calendar.room.code} · {calendar.platform.name}",
                    room_id=calendar.room_id, room_code=calendar.room.code,
                    platform_name=calendar.platform.name, target_url=target,
                ))
            elif state == "overdue":
                incidents.append(DashboardIncident(
                    key=f"calendar-overdue:{calendar.id}", kind="calendar_overdue",
                    severity="attention", title="Sincronización atrasada",
                    detail=f"{calendar.room.code} · {calendar.platform.name}",
                    room_id=calendar.room_id, room_code=calendar.room.code,
                    platform_name=calendar.platform.name, target_url=target,
                ))

            if master_calendar_evidence(calendar, now).state == "recurrent_stale":
                incidents.append(DashboardIncident(
                    key=f"master-stale:{calendar.id}", kind="master_calendar_stale",
                    severity="informational",
                    title="Calendario maestro sin consultas recientes",
                    detail=f"{calendar.room.code} · {calendar.platform.name}",
                    room_id=calendar.room_id, room_code=calendar.room.code,
                    platform_name=calendar.platform.name, target_url=target,
                ))

        unknown_seen = set()
        for booking in bookings:
            if booking.guest_id is not None:
                continue
            relevant = (
                booking.check_in <= today < booking.check_out
                or today <= booking.effective_arrival_date <= movement_end
            )
            if not relevant or booking.id in unknown_seen:
                continue
            unknown_seen.add(booking.id)
            incidents.append(DashboardIncident(
                key=f"unknown-guest:{booking.id}", kind="unknown_guest",
                severity="attention", title="Huésped desconocido",
                detail=(
                    f"{booking.room.code} · entrada "
                    f"{booking.effective_arrival_date.strftime('%d/%m/%Y')}"
                ),
                room_id=booking.room_id, room_code=booking.room.code,
                booking_id=booking.id,
            ))

        incidents.sort(key=lambda item: (
            INCIDENT_PRIORITY[item.severity], item.title, item.room_code, item.key
        ))
        platforms = []
        for item in platform_counts.values():
            platform = item["platform"]
            platforms.append(DashboardPlatformSummary(
                slug=platform.slug,
                name=platform.name,
                favicon=platform_favicon(platform.slug, platform.favicon),
                correct=item["correct"],
                review=item["review"],
            ))
        platforms.sort(key=lambda item: item.name.casefold())

        active_count = len(rooms)
        occupied_count = len(occupied_room_ids)
        return DashboardData(
            today=today,
            summary=DashboardSummary(
                active_rooms=active_count,
                occupied_rooms=occupied_count,
                free_rooms=active_count - occupied_count,
                occupancy_percentage=(
                    round(occupied_count * 100 / active_count, 1)
                    if active_count else 0
                ),
                arrivals_today=sum(item.date == today for item in arrivals),
                departures_today=sum(item.date == today for item in departures),
            ),
            upcoming_arrivals=arrivals,
            upcoming_departures=departures,
            incidents=incidents,
            upcoming_availability=self._availability(
                rooms, bookings, today, availability_end
            ),
            platforms=platforms,
            reliable_last_update=(
                min(reliable_sync_times) if reliable_sync_times else None
            ),
        )
