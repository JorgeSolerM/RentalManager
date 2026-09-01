from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from backend.models.booking_party import BookingParty

from backend.models.booking import Booking
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar


class GanttRepository:
    def list_rooms(
        self,
        db: Session,
        property_id: int | None = None,
        include_inactive: bool = False,
    ) -> list[Room]:
        statement = (
            select(Room)
            .join(Room.property)
            .options(joinedload(Room.property))
            .order_by(Property.name, Room.display_order, Room.code)
        )
        if property_id is not None:
            statement = statement.where(Room.property_id == property_id)
        if not include_inactive:
            statement = statement.where(Room.active.is_(True))
        return list(db.scalars(statement).unique())

    def list_bookings(
        self,
        db: Session,
        room_ids: list[int],
        start: date,
        end: date,
    ) -> list[Booking]:
        if not room_ids:
            return []
        statement = (
            select(Booking)
            .where(
                Booking.room_id.in_(room_ids),
                Booking.check_in < end,
                Booking.check_out > start,
            )
            .options(
                joinedload(Booking.guest),
                joinedload(Booking.parties).joinedload(BookingParty.person),
                joinedload(Booking.room_calendar).joinedload(
                    RoomCalendar.platform
                ),
            )
            .order_by(Booking.room_id, Booking.check_in, Booking.check_out, Booking.id)
        )
        return list(db.scalars(statement).unique())

    def list_room_calendars(
        self, db: Session, room_ids: list[int]
    ) -> list[RoomCalendar]:
        if not room_ids:
            return []
        statement = (
            select(RoomCalendar)
            .where(RoomCalendar.room_id.in_(room_ids))
            .options(joinedload(RoomCalendar.platform))
            .order_by(RoomCalendar.room_id, RoomCalendar.id)
        )
        return list(db.scalars(statement).unique())
