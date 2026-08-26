from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.core.business_time import business_today
from backend.core.platform_favicons import platform_favicon
from backend.core.master_calendar_observation import (
    master_calendar_evidence,
    master_calendar_evidence_label,
)
from datetime import datetime, timezone
from backend.models.room import Room
from backend.repositories.room_repository import RoomRepository
from backend.services.room_calendar_sync_runner import RoomCalendarSyncRunner


SYNC_STATE_LABELS = {
    "ok": "Sincronizado",
    "never_synced": "Nunca sincronizado",
    "error": "Error en última sincronización",
    "overdue": "Sincronización atrasada",
    "paused": "Automatización pausada",
    "inactive": "Calendario inactivo",
    "platform_inactive": "Plataforma inactiva",
    "room_archived": "Pausada por habitación archivada",
}


class RoomService:
    def __init__(self):
        self.repository = RoomRepository()
        self.sync_runner = RoomCalendarSyncRunner()

    def list_rooms(self, db: Session) -> list[Room]:
        return self.repository.get_all(db)

    def list_rooms_by_property(self, db: Session, property_id: int) -> list[Room]:
        return self.repository.get_by_property(db, property_id)

    def list_rooms_with_platform_status(
        self, db: Session, property_id: int
    ) -> list[dict]:
        rooms = self.repository.get_by_property(db, property_id)
        result = []
        for room in rooms:
            integrations = []
            calendars = sorted(
                room.room_calendars,
                key=lambda item: (item.platform.name.casefold(), item.platform.id),
            )
            for calendar in calendars:
                state = self.sync_runner.health_state(calendar)
                outbound = master_calendar_evidence(
                    calendar,
                    datetime.now(timezone.utc).replace(tzinfo=None),
                )
                integrations.append({
                    "platform": calendar.platform,
                    "favicon": platform_favicon(
                        calendar.platform.slug,
                        calendar.platform.favicon,
                    ),
                    "state": state,
                    "operational": state == "ok" and outbound.state == "recurrent_recent",
                    "status_label": SYNC_STATE_LABELS[state],
                    "master_calendar_status_label": (
                        master_calendar_evidence_label(outbound)
                    ),
                })
            result.append({"room": room, "integrations": integrations})
        return result

    def count_rooms_by_property(self, db: Session, property_id: int) -> int:
        return self.repository.count_by_property(db, property_id)

    def count_active_rooms_by_property(self, db: Session, property_id: int) -> int:
        return self.repository.count_active_by_property(db, property_id)

    def get_room(self, db: Session, room_id: int) -> Room | None:
        return self.repository.get_by_id(db, room_id)

    def create_room(self, db: Session, room: Room) -> OperationResult[Room]:
        if self.repository.get_by_code(db, room.code) is not None:
            return OperationResult(success=False, message="code_exists")
        try:
            self.repository.create(db, room)
            db.commit()
            return OperationResult(success=True, data=room)
        except Exception:
            db.rollback()
            raise

    def update_room(
        self, db: Session, room_id: int, code: str,
    ) -> OperationResult[Room]:
        room = self.repository.get_by_id(db, room_id)
        if room is None:
            return OperationResult(success=False, message="not_found")
        existing = self.repository.get_by_code(db, code)
        if existing is not None and existing.id != room.id:
            return OperationResult(success=False, message="code_exists")
        try:
            room.code = code
            self.repository.update(db, room)
            db.commit()
            return OperationResult(success=True, data=room)
        except Exception:
            db.rollback()
            raise

    def archive(self, db: Session, room_id: int) -> OperationResult[Room]:
        room = self.repository.get_by_id(db, room_id)
        if room is None:
            return OperationResult(success=False, message="not_found")
        if not room.active:
            return OperationResult(success=True, data=room)
        if self.repository.has_current_or_future_bookings(
            db, room.id, business_today()
        ):
            return OperationResult(
                success=False,
                message="room_archive_has_current_or_future_bookings",
            )
        try:
            room.active = False
            room.is_published = False
            self.repository.update(db, room)
            db.commit()
            return OperationResult(success=True, data=room)
        except Exception:
            db.rollback()
            raise

    def restore(self, db: Session, room_id: int) -> OperationResult[Room]:
        room = self.repository.get_by_id(db, room_id)
        if room is None:
            return OperationResult(success=False, message="not_found")
        if room.active:
            return OperationResult(success=True, data=room)
        try:
            room.active = True
            room.is_published = False
            self.repository.update(db, room)
            db.commit()
            return OperationResult(success=True, data=room)
        except Exception:
            db.rollback()
            raise

    def put_into_operation(
        self, db: Session, room_id: int
    ) -> OperationResult[Room]:
        room = self.repository.get_by_id(db, room_id)
        if room is None:
            return OperationResult(success=False, message="not_found")
        if not room.active:
            return OperationResult(
                success=False, message="room_archived_cannot_be_operational"
            )
        if room.operational_since is not None:
            return OperationResult(success=True, data=room)
        try:
            room.operational_since = business_today()
            self.repository.update(db, room)
            db.commit()
            return OperationResult(success=True, data=room)
        except Exception:
            db.rollback()
            raise

    def delete_room(self, db: Session, room_id: int) -> OperationResult[None]:
        room = self.repository.get_by_id(db, room_id)
        if room is None:
            return OperationResult(success=False, message="not_found")
        if self.repository.has_bookings(db, room.id):
            return OperationResult(success=False, message="room_has_bookings")
        if self.repository.has_room_calendars(db, room.id):
            return OperationResult(success=False, message="room_has_room_calendars")
        try:
            self.repository.delete(db, room)
            db.commit()
            return OperationResult(success=True)
        except Exception:
            db.rollback()
            raise
