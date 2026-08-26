from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.models.booking import Booking
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar
from backend.repositories.base_repository import BaseRepository


class RoomRepository(BaseRepository):

    def get_all(
        self,
        db: Session,
    ) -> list[Room]:

        statement = (
            select(Room)
            .order_by(
                Room.property_id,
                Room.display_order,
            )
        )

        return db.scalars(statement).all()

    def get_by_property(
        self,
        db: Session,
        property_id: int,
    ) -> list[Room]:

        statement = (
            select(Room)
            .options(
                selectinload(Room.room_calendars).joinedload(
                    RoomCalendar.platform
                )
            )
            .where(Room.property_id == property_id)
            .order_by(Room.display_order, Room.code)
        )

        return db.scalars(statement).all()

    def count_by_property(
        self,
        db: Session,
        property_id: int,
    ) -> int:

        statement = (
            select(func.count())
            .select_from(Room)
            .where(Room.property_id == property_id)
        )

        return db.scalar(statement) or 0

    def count_active_by_property(
        self,
        db: Session,
        property_id: int,
    ) -> int:
        statement = (
            select(func.count())
            .select_from(Room)
            .where(
                Room.property_id == property_id,
                Room.active.is_(True),
            )
        )
        return db.scalar(statement) or 0

    def get_by_id(
        self,
        db: Session,
        room_id: int,
    ) -> Room | None:

        statement = (
            select(Room)
            .where(Room.id == room_id)
        )

        return db.scalar(statement)

    def get_by_code(
        self,
        db: Session,
        code: str,
    ) -> Room | None:

        statement = (
            select(Room)
            .where(Room.code == code)
        )

        return db.scalar(statement)

    def get_by_master_calendar_token(
        self,
        db: Session,
        token: str,
    ) -> Room | None:
        return db.scalar(
            select(Room).where(Room.master_calendar_token == token)
        )

    def has_bookings(
        self,
        db: Session,
        room_id: int,
    ) -> bool:

        statement = (
            select(func.count())
            .select_from(Booking)
            .where(Booking.room_id == room_id)
        )

        return (db.scalar(statement) or 0) > 0

    def has_current_or_future_bookings(
        self,
        db: Session,
        room_id: int,
        business_date: date,
    ) -> bool:
        """Use contractual dates; checkout on the business date is historical."""
        statement = (
            select(Booking.id)
            .where(
                Booking.room_id == room_id,
                Booking.check_out > business_date,
            )
            .limit(1)
        )
        return db.scalar(statement) is not None

    def has_room_calendars(
        self,
        db: Session,
        room_id: int,
    ) -> bool:

        statement = (
            select(func.count())
            .select_from(RoomCalendar)
            .where(RoomCalendar.room_id == room_id)
        )

        return (db.scalar(statement) or 0) > 0
