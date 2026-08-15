from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.models.booking import Booking
from backend.schemas.booking_schema import BookingResponse
from backend.services.booking_service import BookingService
from backend.services.guest_service import GuestService

router = APIRouter(prefix="/bookings")

booking_service = BookingService()
guest_service = GuestService()


@router.get("/room/{room_id}")
def list_bookings(room_id: int, db: Session = Depends(get_db)):

    return booking_service.list_bookings_by_room(
        db,
        room_id,
    )


@router.get(
    "/{booking_id}",
    response_model=BookingResponse,
)
def get_booking(
    booking_id: int,
    db: Session = Depends(get_db),
):

    booking = booking_service.get_booking(
        db,
        booking_id,
    )

    if booking is None:

        raise HTTPException(
            status_code=404,
            detail="Reserva no encontrada.",
        )

    return BookingResponse(

        id=booking.id,

        room_id=booking.room_id,

        guest_name=booking.guest.full_name,

        origin=booking.origin,

        check_in=booking.check_in,

        check_out=booking.check_out,

        price=booking.price,

        notes=booking.notes,

    )


@router.post("/create")
def create_booking(

    room_id: int = Form(...),

    guest_name: str = Form(...),

    check_in: date = Form(...),

    check_out: date = Form(...),

    price: float | None = Form(None),

    notes: str | None = Form(None),
    db: Session = Depends(get_db),

):

    guest = guest_service.get_or_create_guest(
        db,
        guest_name,
    )

    booking = Booking(
        room_id=room_id,
    )

    booking_service.populate_booking(

        booking=booking,

        guest=guest,

        check_in=check_in,

        check_out=check_out,

        price=price,

        notes=notes,

    )

    booking_service.create_booking(
        db,
        booking,
    )

    return RedirectResponse(
    url=f"/rooms/{room_id}?success=booking_created",
    status_code=303,
    )


@router.post("/update/{booking_id}")
def update_booking(

    booking_id: int,

    room_id: int = Form(...),

    guest_name: str = Form(...),

    check_in: date = Form(...),

    check_out: date = Form(...),

    price: float | None = Form(None),

    notes: str | None = Form(None),
    db: Session = Depends(get_db),

):

    booking = booking_service.get_booking(
        db,
        booking_id,
    )

    if booking is None:

        raise HTTPException(
            status_code=404,
            detail="Reserva no encontrada.",
        )

    guest = guest_service.get_or_create_guest(
        db,
        guest_name,
    )

    booking_service.populate_booking(

        booking=booking,

        guest=guest,

        check_in=check_in,

        check_out=check_out,

        price=price,

        notes=notes,

    )

    booking_service.update_booking(
        db,
        booking,
    )

    return RedirectResponse(
    url=f"/rooms/{room_id}?success=booking_updated",
    status_code=303,
    )

@router.post("/delete/{booking_id}")
def delete_booking(
    booking_id: int,
    db: Session = Depends(get_db),
):

    booking = booking_service.get_booking(
        db,
        booking_id,
    )

    if booking is None:

        raise HTTPException(
            status_code=404,
            detail="Reserva no encontrada.",
        )

    room_id = booking.room_id

    booking_service.delete_booking(
        db,
        booking,
    )

    return RedirectResponse(
    url=f"/rooms/{room_id}?success=booking_deleted",
    status_code=303,
    )
