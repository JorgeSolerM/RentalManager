from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, aliased, joinedload

from backend.models.booking import Booking
from backend.models.property import Property
from backend.models.room import Room
from backend.models.room_calendar import RoomCalendar


class DashboardRepository:
    def list_active_rooms(self, db: Session) -> list[Room]:
        return list(db.scalars(
            select(Room)
            .join(Room.property)
            .options(joinedload(Room.property))
            .where(Room.active.is_(True))
            .order_by(Property.name, Room.display_order, Room.code)
        ).unique())

    def list_operational_bookings(
        self, db: Session, today: date, availability_end: date
    ) -> list[Booking]:
        return list(db.scalars(
            select(Booking)
            .join(Booking.room)
            .options(
                joinedload(Booking.guest),
                joinedload(Booking.room).joinedload(Room.property),
                joinedload(Booking.room_calendar).joinedload(
                    RoomCalendar.platform
                ),
            )
            .where(
                Room.active.is_(True),
                Booking.check_in <= availability_end,
                Booking.check_out >= today,
            )
            .order_by(Booking.check_in, Booking.check_out, Booking.id)
        ).unique())

    def list_room_calendars(self, db: Session) -> list[RoomCalendar]:
        return list(db.scalars(
            select(RoomCalendar)
            .join(RoomCalendar.room)
            .options(
                joinedload(RoomCalendar.platform),
                joinedload(RoomCalendar.room).joinedload(Room.property),
            )
            .where(Room.active.is_(True))
            .order_by(RoomCalendar.room_id, RoomCalendar.platform_id)
        ).unique())

    def list_operational_overlaps(self, db: Session, today: date) -> list[dict]:
        first = aliased(Booking)
        second = aliased(Booking)
        rows = db.execute(
            select(
                first.id.label("first_booking_id"),
                second.id.label("second_booking_id"),
                Room.id.label("room_id"),
                Room.code.label("room_code"),
                Property.name.label("property_name"),
                first.check_in.label("first_check_in"),
                first.check_out.label("first_check_out"),
                second.check_in.label("second_check_in"),
                second.check_out.label("second_check_out"),
            )
            .join(second, and_(
                first.id < second.id,
                first.room_id == second.room_id,
                first.check_in < second.check_out,
                first.check_out > second.check_in,
                first.check_out > today,
                second.check_out > today,
            ))
            .join(Room, Room.id == first.room_id)
            .join(Property, Property.id == Room.property_id)
            .where(Room.active.is_(True))
            .order_by(Property.name, Room.display_order, Room.code, first.id)
        ).mappings()
        return [dict(row) for row in rows]
