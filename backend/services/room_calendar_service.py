from urllib.parse import urlparse

from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.models.platform import Platform
from backend.models.room_calendar import RoomCalendar
from backend.repositories.platform_repository import PlatformRepository
from backend.repositories.room_calendar_repository import RoomCalendarRepository
from backend.repositories.room_repository import RoomRepository


class RoomCalendarService:
    def __init__(self):
        self.repository = RoomCalendarRepository()
        self.room_repository = RoomRepository()
        self.platform_repository = PlatformRepository()

    def get_by_id(self, db: Session, calendar_id: int) -> RoomCalendar | None:
        return self.repository.get_by_id(db, calendar_id)

    def list_configurations(self, db: Session, room_id: int) -> list[dict]:
        calendars = {
            calendar.platform_id: calendar
            for calendar in self.repository.list_by_room(db, room_id)
        }
        return [
            {"platform": platform, "calendar": calendars.get(platform.id)}
            for platform in self.platform_repository.get_all(db)
        ]

    @staticmethod
    def _normalize_url(value: str | None) -> str | None:
        normalized = value.strip() if value else ""
        return normalized or None

    def _validate_urls(
        self,
        platform: Platform,
        import_url: str | None,
        export_url: str | None,
    ) -> tuple[str | None, str | None, str | None]:
        import_url = self._normalize_url(import_url)
        export_url = self._normalize_url(export_url)
        if import_url is None and export_url is None:
            return import_url, export_url, "room_calendar_url_required"
        if import_url is not None and not platform.supports_import:
            return import_url, export_url, "room_calendar_import_not_supported"
        if export_url is not None and not platform.supports_export:
            return import_url, export_url, "room_calendar_export_not_supported"
        for value in (import_url, export_url):
            if value is not None:
                parsed = urlparse(value)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    return import_url, export_url, "room_calendar_invalid_url"
        return import_url, export_url, None

    def create_calendar(
        self,
        db: Session,
        room_id: int,
        platform_id: int,
        import_url: str | None,
        export_url: str | None,
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
        import_url, export_url, error = self._validate_urls(
            platform, import_url, export_url
        )
        if error:
            return OperationResult(success=False, message=error)
        calendar = RoomCalendar(
            room_id=room_id,
            platform_id=platform_id,
            import_url=import_url,
            export_url=export_url,
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
        export_url: str | None,
    ) -> OperationResult[RoomCalendar]:
        calendar = self.repository.get_by_id(db, calendar_id)
        if calendar is None:
            return OperationResult(success=False, message="not_found")
        import_url, export_url, error = self._validate_urls(
            calendar.platform, import_url, export_url
        )
        if error:
            return OperationResult(success=False, message=error, data=calendar)
        try:
            calendar.import_url = import_url
            calendar.export_url = export_url
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
