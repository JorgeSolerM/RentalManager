from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.repositories.room_calendar_repository import RoomCalendarRepository


class MasterCalendarObservationService:
    def __init__(self, now_factory=None):
        self.repository = RoomCalendarRepository()
        self.now_factory = now_factory or (
            lambda: datetime.now(timezone.utc).replace(tzinfo=None)
        )

    def observe(self, db: Session, room_id: int, platform_id: int) -> bool:
        try:
            calendar = self.repository.get_by_room_and_platform(
                db, room_id, platform_id
            )
            if calendar is None:
                db.rollback()
                return False
            observed_at = self.now_factory()
            if calendar.master_calendar_first_request_at is None:
                calendar.master_calendar_first_request_at = observed_at
            calendar.last_master_calendar_request_at = observed_at
            calendar.master_calendar_request_count += 1
            self.repository.update(db, calendar)
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False
