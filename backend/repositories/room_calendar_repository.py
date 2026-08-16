from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.models.booking import Booking
from backend.models.room_calendar import RoomCalendar
from backend.repositories.base_repository import BaseRepository


class RoomCalendarRepository(BaseRepository):
    def get_by_id(self, db: Session, calendar_id: int) -> RoomCalendar | None:
        return db.scalar(select(RoomCalendar).where(RoomCalendar.id == calendar_id))

    def get_by_room_and_platform(
        self, db: Session, room_id: int, platform_id: int
    ) -> RoomCalendar | None:
        return db.scalar(
            select(RoomCalendar).where(
                RoomCalendar.room_id == room_id,
                RoomCalendar.platform_id == platform_id,
            )
        )

    def list_by_room(self, db: Session, room_id: int) -> list[RoomCalendar]:
        return db.scalars(
            select(RoomCalendar).where(RoomCalendar.room_id == room_id)
        ).all()

    def has_bookings(self, db: Session, calendar_id: int) -> bool:
        return db.scalar(
            select(Booking.id)
            .where(Booking.room_calendar_id == calendar_id)
            .limit(1)
        ) is not None

    def has_incompatible_urls(
        self,
        db: Session,
        platform_id: int,
        supports_import: bool,
        supports_export: bool,
    ) -> bool:
        statement = select(RoomCalendar.id).where(
            RoomCalendar.platform_id == platform_id
        )
        incompatible_conditions = []
        if not supports_import:
            incompatible_conditions.append(RoomCalendar.import_url.is_not(None))
        if not supports_export:
            incompatible_conditions.append(RoomCalendar.export_url.is_not(None))
        if not incompatible_conditions:
            return False
        return db.scalar(
            statement.where(or_(*incompatible_conditions)).limit(1)
        ) is not None
