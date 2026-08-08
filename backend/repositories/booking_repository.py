from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.booking import Booking
from backend.repositories.base_repository import BaseRepository


class BookingRepository(BaseRepository):

    def get_by_id(
        self,
        db: Session,
        booking_id: int,
    ) -> Booking | None:

        statement = (
            select(Booking)
            .where(Booking.id == booking_id)
        )

        return db.scalar(statement)

    def list_by_room(
        self,
        db: Session,
        room_id: int,
    ) -> list[Booking]:

        statement = (
            select(Booking)
            .where(Booking.room_id == room_id)
            .order_by(Booking.check_in)
        )

        return db.scalars(statement).all()

    def list_current(
        self,
        db: Session,
        room_id: int,
        today: date,
    ) -> list[Booking]:

        statement = (
            select(Booking)
            .where(Booking.room_id == room_id)
            .where(Booking.check_in <= today)
            .where(Booking.check_out > today)
        )

        return db.scalars(statement).all()

    def list_future(
        self,
        db: Session,
        room_id: int,
        today: date,
    ) -> list[Booking]:

        statement = (
            select(Booking)
            .where(Booking.room_id == room_id)
            .where(Booking.check_in > today)
            .order_by(Booking.check_in)
        )

        return db.scalars(statement).all()
