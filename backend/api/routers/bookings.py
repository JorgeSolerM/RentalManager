from datetime import date

from fastapi import APIRouter, Form, HTTPException
from fastapi.responses import RedirectResponse

from backend.database.session import SessionLocal
from backend.models.booking import Booking
from backend.services.booking_service import BookingService
from backend.services.guest_service import GuestService

router = APIRouter(prefix="/bookings")

booking_service = BookingService()
guest_service = GuestService()


@router.get("/room/{room_id}")
def list_bookings(room_id: int):

    db = SessionLocal()

    try:

        return booking_service.list_bookings_by_room(
            db,
            room_id,
        )

    finally:

        db.close()


@router.get("/{booking_id}")
def get_booking(booking_id: int):

    db = SessionLocal()

    try:

        booking = booking_service.get_booking(
            db,
            booking_id,
        )

        if booking is None:

            raise HTTPException(
                status_code=404,
                detail="Reserva no encontrada.",
            )

        return booking

    finally:

        db.close()


@router.post("/create")
def create_booking(

    room_id: int = Form(...),

    guest_name: str = Form(...),

    check_in: date = Form(...),

    check_out: date = Form(...),

    price: float | None = Form(None),

    notes: str | None = Form(None),

):
    print(">>> Entrando en create_booking")

    db = SessionLocal()

    try:

        guest = guest_service.get_or_create_guest(
            db,
            guest_name,
        )

        booking = Booking(

            room_id=room_id,

            guest_id=guest.id,

            room_calendar_id=None,

            origin="manual",

            check_in=check_in,

            check_out=check_out,

            price=price,

            notes=notes,

        )

        booking_service.create_booking(
            db,
            booking,
        )

    finally:

        db.close()

    return RedirectResponse(
        url=f"/rooms/{room_id}",
        status_code=303,
    )
