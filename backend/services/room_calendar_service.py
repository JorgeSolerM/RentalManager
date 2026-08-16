from urllib.parse import urlparse

from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.models.platform import Platform
from backend.models.room_calendar import RoomCalendar
from backend.repositories.platform_repository import PlatformRepository
from backend.repositories.room_calendar_repository import RoomCalendarRepository
from backend.repositories.room_repository import RoomRepository
from backend.services.room_calendar_sync_runner import RoomCalendarSyncRunner


class RoomCalendarService:
    def __init__(self):
        self.repository = RoomCalendarRepository()
        self.room_repository = RoomRepository()
        self.platform_repository = PlatformRepository()
        self.sync_runner = RoomCalendarSyncRunner()

    def get_by_id(self, db: Session, calendar_id: int) -> RoomCalendar | None:
        return self.repository.get_by_id(db, calendar_id)

    def list_configurations(self, db: Session, room_id: int) -> list[dict]:
        calendars = {
            calendar.platform_id: calendar
            for calendar in self.repository.list_by_room(db, room_id)
        }
        configurations = []
        for platform in self.platform_repository.get_all(db):
            calendar = calendars.get(platform.id)
            configurations.append({
                "platform": platform,
                "calendar": calendar,
                "automatic_active": bool(
                    calendar
                    and calendar.active
                    and calendar.automatic_sync_enabled
                    and calendar.import_url
                    and calendar.room.active
                    and platform.active
                ),
                "overdue": bool(
                    calendar and self.sync_runner.is_overdue(calendar)
                ),
                "last_sync_error_text": (
                    self.sync_runner.error_message(calendar.last_sync_error)
                    if calendar
                    else None
                ),
            })
        return configurations

    @staticmethod
    def _normalize_url(value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        return normalized or None

    def _validate_urls(
        self,
        platform: Platform,
        import_url: str | None,
    ) -> tuple[str | None, str | None]:
        import_url = self._normalize_url(import_url)
        if platform.supports_import and import_url is None:
            return import_url, "room_calendar_import_url_required"
        if import_url is not None and not platform.supports_import:
            return import_url, "room_calendar_import_not_supported"
        if import_url is not None:
            parsed = urlparse(import_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return import_url, "room_calendar_invalid_url"
        return import_url, None

    def create_calendar(
        self,
        db: Session,
        room_id: int,
        platform_id: int,
        import_url: str | None,
    ) -> OperationResult[RoomCalendar]:
        room = self.room_repository.get_by_id(db, room_id)
        if room is None:
            return OperationResult(success=False, message="room_not_found")
        if not room.active:
            return OperationResult(success=False, message="room_calendar_room_inactive")
        platform = self.platform_repository.get_by_id(db, platform_id)
        if platform is None:
            return OperationResult(success=False, message="platform_not_found")
        if not platform.active:
            return OperationResult(success=False, message="room_calendar_platform_inactive")
        if self.repository.get_by_room_and_platform(db, room_id, platform_id):
            return OperationResult(success=False, message="room_calendar_exists")
        import_url, error = self._validate_urls(platform, import_url)
        if error:
            return OperationResult(success=False, message=error)
        calendar = RoomCalendar(
            room_id=room_id,
            platform_id=platform_id,
            import_url=import_url,
            active=True,
        )
        try:
            self.repository.create(db, calendar)
            db.commit()
            return OperationResult(success=True, data=calendar)
        except Exception:
            db.rollback()
            raise

    def update_calendar(
        self,
        db: Session,
        calendar_id: int,
        import_url: str | None,
    ) -> OperationResult[RoomCalendar]:
        calendar = self.repository.get_by_id(db, calendar_id)
        if calendar is None:
            return OperationResult(success=False, message="not_found")
        import_url, error = self._validate_urls(calendar.platform, import_url)
        if error:
            return OperationResult(success=False, message=error, data=calendar)
        try:
            url_changed = calendar.import_url != import_url
            calendar.import_url = import_url
            if url_changed:
                calendar.last_sync_attempt_at = None
                calendar.last_sync_status = None
                calendar.last_sync_error = None
                calendar.consecutive_failures = 0
            self.repository.update(db, calendar)
            db.commit()
            return OperationResult(success=True, data=calendar)
        except Exception:
            db.rollback()
            raise

    def toggle_automatic_sync(
        self, db: Session, calendar_id: int
    ) -> OperationResult[RoomCalendar]:
        calendar = self.repository.get_by_id(db, calendar_id)
        if calendar is None:
            return OperationResult(success=False, message="not_found")
        if not calendar.automatic_sync_enabled:
            if (
                not calendar.active
                or not calendar.room.active
                or not calendar.platform.active
                or not calendar.platform.supports_import
                or not calendar.import_url
            ):
                return OperationResult(
                    success=False,
                    message="room_calendar_automatic_unavailable",
                    data=calendar,
                )
        try:
            calendar.automatic_sync_enabled = not calendar.automatic_sync_enabled
            self.repository.update(db, calendar)
            db.commit()
            return OperationResult(success=True, data=calendar)
        except Exception:
            db.rollback()
            raise

    def toggle_calendar(
        self, db: Session, calendar_id: int
    ) -> OperationResult[RoomCalendar]:
        calendar = self.repository.get_by_id(db, calendar_id)
        if calendar is None:
            return OperationResult(success=False, message="not_found")
        if not calendar.active:
            if not calendar.room.active:
                return OperationResult(
                    success=False,
                    message="room_calendar_room_inactive",
                    data=calendar,
                )
            if not calendar.platform.active:
                return OperationResult(
                    success=False,
                    message="room_calendar_platform_inactive",
                    data=calendar,
                )
        try:
            calendar.active = not calendar.active
            self.repository.update(db, calendar)
            db.commit()
            return OperationResult(success=True, data=calendar)
        except Exception:
            db.rollback()
            raise

    def delete_calendar(
        self, db: Session, calendar_id: int
    ) -> OperationResult[RoomCalendar]:
        calendar = self.repository.get_by_id(db, calendar_id)
        if calendar is None:
            return OperationResult(success=False, message="not_found")
        if self.repository.has_bookings(db, calendar_id):
            return OperationResult(
                success=False,
                message="room_calendar_has_bookings",
                data=calendar,
            )
        try:
            self.repository.delete(db, calendar)
            db.commit()
            return OperationResult(success=True, data=calendar)
        except Exception:
            db.rollback()
            raise
