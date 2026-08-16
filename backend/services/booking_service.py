from datetime import date
import math

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend.core.operation_result import OperationResult
from backend.models.booking import Booking
from backend.models.guest import Guest
from backend.repositories.booking_repository import BookingRepository
from backend.repositories.guest_repository import GuestRepository
from backend.repositories.room_repository import RoomRepository
from backend.repositories.room_calendar_repository import RoomCalendarRepository


class BookingService:
    def __init__(self):
        self.booking_repository = BookingRepository()
        self.guest_repository = GuestRepository()
        self.room_repository = RoomRepository()
        self.room_calendar_repository = RoomCalendarRepository()

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

    def _validate_booking(
        self,
        db: Session,
        room_id: int,
        check_in: date,
        check_out: date,
        price: float | None,
        manual_guest_present: bool,
        exclude_booking_id: int | None = None,
    ) -> str | None:
        if check_out <= check_in:
            return "booking_invalid_dates"

        room = self.room_repository.get_by_id(db, room_id)
        if room is None:
            return "booking_room_not_found"
        if not room.active:
            return "booking_room_inactive"
        if not manual_guest_present:
            return "booking_guest_required"
        if price is not None and (not math.isfinite(price) or price < 0):
            return "booking_invalid_price"
        if self.booking_repository.has_overlap(
            db,
            room_id,
            check_in,
            check_out,
            exclude_booking_id=exclude_booking_id,
        ):
            return "booking_overlap"
        return None

    @staticmethod
    def _rejected(
        db: Session,
        message: str,
        booking: Booking | None = None,
    ) -> OperationResult[Booking]:
        db.rollback()
        return OperationResult(success=False, message=message, data=booking)

    @staticmethod
    def _is_manual(booking: Booking) -> bool:
        return booking.origin == "manual" and booking.room_calendar_id is None

    @staticmethod
    def _is_overlap_error(error: IntegrityError) -> bool:
        return "booking_overlap" in str(error.orig)

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

    def get_booking(self, db: Session, booking_id: int) -> Booking | None:
        return self.booking_repository.get_by_id(db, booking_id)

    def list_bookings_by_room(self, db: Session, room_id: int) -> list[Booking]:
        return self.booking_repository.list_by_room(db, room_id)

    def create_booking(
        self,
        db: Session,
        booking: Booking,
    ) -> OperationResult[Booking]:
        try:
            validation_error = self._validate_booking(
                db,
                booking.room_id,
                booking.check_in,
                booking.check_out,
                booking.price,
                manual_guest_present=(
                    not self._is_manual(booking) or booking.guest_id is not None
                ),
            )
            if validation_error:
                return self._rejected(db, validation_error, booking)
            self.booking_repository.create(db, booking)
            db.commit()
            return OperationResult(success=True, data=booking)
        except IntegrityError as error:
            db.rollback()
            if self._is_overlap_error(error):
                return OperationResult(success=False, message="booking_overlap")
            raise
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
    ) -> OperationResult[Booking]:
        try:
            stripped_guest_name = guest_name.strip()
            validation_error = self._validate_booking(
                db,
                room_id,
                check_in,
                check_out,
                price,
                manual_guest_present=bool(stripped_guest_name),
            )
            if validation_error:
                return self._rejected(db, validation_error)
            guest = self._get_or_create_guest(db, stripped_guest_name)
            booking = Booking(room_id=room_id)
            self.populate_booking(
                booking, guest, check_in, check_out, price, notes
            )
            self.booking_repository.create(db, booking)
            db.commit()
            return OperationResult(success=True, data=booking)
        except IntegrityError as error:
            db.rollback()
            if self._is_overlap_error(error):
                return OperationResult(success=False, message="booking_overlap")
            raise
        except Exception:
            db.rollback()
            raise

    def update_booking(
        self,
        db: Session,
        booking: Booking,
    ) -> OperationResult[Booking]:
        try:
            validation_error = self._validate_booking(
                db,
                booking.room_id,
                booking.check_in,
                booking.check_out,
                booking.price,
                manual_guest_present=(
                    not self._is_manual(booking) or booking.guest_id is not None
                ),
                exclude_booking_id=booking.id,
            )
            if validation_error:
                return self._rejected(db, validation_error, booking)
            self.booking_repository.update(db, booking)
            db.commit()
            return OperationResult(success=True, data=booking)
        except IntegrityError as error:
            db.rollback()
            if self._is_overlap_error(error):
                return OperationResult(success=False, message="booking_overlap")
            raise
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
    ) -> OperationResult[Booking]:
        try:
            booking = self.booking_repository.get_by_id(db, booking_id)
            if booking is None:
                return self._rejected(db, "not_found")
            if not self._is_manual(booking):
                return self._rejected(db, "booking_imported_read_only", booking)

            stripped_guest_name = guest_name.strip()
            validation_error = self._validate_booking(
                db,
                booking.room_id,
                check_in,
                check_out,
                price,
                manual_guest_present=bool(stripped_guest_name),
                exclude_booking_id=booking.id,
            )
            if validation_error:
                return self._rejected(db, validation_error, booking)

            guest = self._get_or_create_guest(db, stripped_guest_name)
            self.populate_booking(
                booking, guest, check_in, check_out, price, notes
            )
            self.booking_repository.update(db, booking)
            db.commit()
            return OperationResult(success=True, data=booking)
        except IntegrityError as error:
            db.rollback()
            if self._is_overlap_error(error):
                return OperationResult(success=False, message="booking_overlap")
            raise
        except Exception:
            db.rollback()
            raise

    def upsert_imported_booking(
        self,
        db: Session,
        room_calendar_id: int,
        external_reference: str,
        check_in: date,
        check_out: date,
        price: float | None = None,
        notes: str | None = None,
    ) -> OperationResult[Booking]:
        reference = external_reference.strip()
        if not reference:
            return self._rejected(db, "booking_external_reference_required")
        try:
            calendar = self.room_calendar_repository.get_by_id(db, room_calendar_id)
            if calendar is None:
                return self._rejected(db, "room_calendar_not_found")
            if not calendar.active:
                return self._rejected(db, "room_calendar_inactive")
            if not calendar.room.active:
                return self._rejected(db, "booking_room_inactive")
            if not calendar.platform.active:
                return self._rejected(db, "room_calendar_platform_inactive")

            booking = self.booking_repository.get_by_external_reference(
                db, calendar.id, reference
            )
            validation_error = self._validate_booking(
                db,
                calendar.room_id,
                check_in,
                check_out,
                price,
                manual_guest_present=True,
                exclude_booking_id=booking.id if booking else None,
            )
            if validation_error:
                return self._rejected(db, validation_error, booking)

            if booking is None:
                booking = Booking(
                    room_id=calendar.room_id,
                    room_calendar_id=calendar.id,
                    guest_id=None,
                    origin=calendar.platform.slug,
                    external_reference=reference,
                    check_in=check_in,
                    check_out=check_out,
                    price=price,
                    notes=notes,
                )
                self.booking_repository.create(db, booking)
            else:
                booking.check_in = check_in
                booking.check_out = check_out
                booking.price = price
                booking.notes = notes
                self.booking_repository.update(db, booking)

            db.commit()
            return OperationResult(success=True, data=booking)
        except IntegrityError as error:
            db.rollback()
            if self._is_overlap_error(error):
                return OperationResult(success=False, message="booking_overlap")
            raise
        except Exception:
            db.rollback()
            raise

    def delete_booking(
        self,
        db: Session,
        booking: Booking,
    ) -> OperationResult[None]:
        return OperationResult(success=False, message="booking_delete_not_allowed")

    def get_current_booking(self, db: Session, room_id: int) -> Booking | None:
        bookings = self.booking_repository.list_current(db, room_id, date.today())
        return bookings[0] if bookings else None

    def get_future_bookings(self, db: Session, room_id: int) -> list[Booking]:
        return self.booking_repository.list_future(db, room_id, date.today())
