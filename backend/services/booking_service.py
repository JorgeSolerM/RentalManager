from datetime import date

from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.models.booking import Booking
from backend.models.guest import Guest
from backend.repositories.booking_repository import BookingRepository
from backend.repositories.guest_repository import GuestRepository


class BookingService:

    def __init__(self):

        self.booking_repository = BookingRepository()
        self.guest_repository = GuestRepository()

    def _get_or_create_guest(self, db: Session, full_name: str) -> Guest:
        full_name = full_name.strip()
        guest = self.guest_repository.get_by_full_name(db, full_name)
        if guest is None:
            guest = Guest(
                full_name=full_name,
                display_name=full_name,
                active=True,
            )
            self.guest_repository.create(db, guest)
        return guest

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

        try:
            if booking.check_out <= booking.check_in:
                raise ValueError(
                    "La fecha de salida debe ser posterior a la fecha de entrada."
                )
            self.booking_repository.create(db, booking)
            db.commit()
            return booking
        except Exception:
            db.rollback()
            raise

    def create_manual_booking(
        self,
        db: Session,
        room_id: int,
        guest_name: str,
        check_in: date,
        check_out: date,
        price: float | None,
        notes: str | None,
    ) -> Booking:
        try:
            if check_out <= check_in:
                raise ValueError(
                    "La fecha de salida debe ser posterior a la fecha de entrada."
                )
            guest = self._get_or_create_guest(db, guest_name)
            booking = Booking(room_id=room_id)
            self.populate_booking(
                booking, guest, check_in, check_out, price, notes
            )
            self.booking_repository.create(db, booking)
            db.commit()
            return booking
        except Exception:
            db.rollback()
            raise

    def update_booking(
        self,
        db: Session,
        booking: Booking,
    ) -> Booking:

        try:
            if booking.check_out <= booking.check_in:
                raise ValueError(
                    "La fecha de salida debe ser posterior a la fecha de entrada."
                )
            self.booking_repository.update(db, booking)
            db.commit()
            return booking
        except Exception:
            db.rollback()
            raise

    def update_manual_booking(
        self,
        db: Session,
        booking_id: int,
        guest_name: str,
        check_in: date,
        check_out: date,
        price: float | None,
        notes: str | None,
    ) -> Booking | None:
        try:
            booking = self.booking_repository.get_by_id(db, booking_id)
            if booking is None:
                return None
            if check_out <= check_in:
                raise ValueError(
                    "La fecha de salida debe ser posterior a la fecha de entrada."
                )
            guest = self._get_or_create_guest(db, guest_name)
            self.populate_booking(
                booking, guest, check_in, check_out, price, notes
            )
            self.booking_repository.update(db, booking)
            db.commit()
            return booking
        except Exception:
            db.rollback()
            raise

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
