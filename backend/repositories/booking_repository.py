from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.booking import Booking
from backend.repositories.base_repository import BaseRepository


class BookingRepository(BaseRepository):

    def has_overlap(
        self,
        db: Session,
        room_id: int,
        check_in: date,
        check_out: date,
        exclude_booking_id: int | None = None,
    ) -> bool:
        statement = (
            select(Booking.id)
            .where(Booking.room_id == room_id)
            .where(Booking.check_in < check_out)
            .where(Booking.check_out > check_in)
            .limit(1)
        )

        if exclude_booking_id is not None:
            statement = statement.where(Booking.id != exclude_booking_id)

        return db.scalar(statement) is not None

    def get_by_external_reference(
        self,
        db: Session,
        room_calendar_id: int,
        external_reference: str,
    ) -> Booking | None:
        return db.scalar(
            select(Booking).where(
                Booking.room_calendar_id == room_calendar_id,
                Booking.external_reference == external_reference,
            )
        )

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
