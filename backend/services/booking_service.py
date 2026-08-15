from datetime import date

from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.models.booking import Booking
from backend.models.guest import Guest
from backend.repositories.booking_repository import BookingRepository


class BookingService:

    def __init__(self):

        self.booking_repository = BookingRepository()

    def populate_booking(
        self,
        booking: Booking,
        guest: Guest,
        check_in: date,
        check_out: date,
        price: float | None,
        notes: str | None,
    ) -> None:

        booking.guest_id = guest.id

        booking.room_calendar_id = None

        booking.origin = "manual"

        booking.check_in = check_in

        booking.check_out = check_out

        booking.price = price

        booking.notes = notes

    def get_booking(
        self,
        db: Session,
        booking_id: int,
    ) -> Booking | None:

        return self.booking_repository.get_by_id(
            db,
            booking_id,
        )

    def list_bookings_by_room(
        self,
        db: Session,
        room_id: int,
    ) -> list[Booking]:

        return self.booking_repository.list_by_room(
            db,
            room_id,
        )

    def create_booking(
        self,
        db: Session,
        booking: Booking,
    ) -> Booking:

        if booking.check_out <= booking.check_in:

            raise ValueError(
                "La fecha de salida debe ser posterior a la fecha de entrada."
            )

        return self.booking_repository.create(
            db,
            booking,
        )

    def update_booking(
        self,
        db: Session,
        booking: Booking,
    ) -> Booking:

        if booking.check_out <= booking.check_in:

            raise ValueError(
                "La fecha de salida debe ser posterior a la fecha de entrada."
            )

        return self.booking_repository.update(
            db,
            booking,
        )

    def delete_booking(
        self,
        db: Session,
        booking: Booking,
    ) -> OperationResult[None]:

        return OperationResult(
            success=False,
            message="booking_delete_not_allowed",
        )



    def get_current_booking(
        self,
        db: Session,
        room_id: int,
    ) -> Booking | None:

        today = date.today()

        bookings = self.booking_repository.list_current(
            db,
            room_id,
            today,
        )

        if bookings:

            return bookings[0]

        return None

    def get_future_bookings(
        self,
        db: Session,
        room_id: int,
    ) -> list[Booking]:

        today = date.today()

        return self.booking_repository.list_future(
            db,
            room_id,
            today,
        )
