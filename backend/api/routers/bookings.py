from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.schemas.booking_schema import BookingResponse
from backend.services.booking_service import BookingService

router = APIRouter(prefix="/bookings")

booking_service = BookingService()


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

        guest_name=booking.guest.full_name if booking.guest is not None else None,

        origin=booking.origin,

        check_in=booking.check_in,

        check_out=booking.check_out,

        price=booking.price,

        notes=booking.notes,

        editable=booking_service.is_manual_booking(booking),

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

    result = booking_service.create_manual_booking(
        db, room_id, guest_name, check_in, check_out, price, notes
    )

    if not result.success:
        return RedirectResponse(
            url=f"/rooms/{room_id}?error={result.message}",
            status_code=303,
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

    result = booking_service.update_manual_booking(
        db, booking_id, guest_name, check_in, check_out, price, notes
    )

    if not result.success and result.message == "not_found":

        raise HTTPException(
            status_code=404,
            detail="Reserva no encontrada.",
        )

    authoritative_room_id = result.data.room_id

    if not result.success:
        return RedirectResponse(
            url=f"/rooms/{authoritative_room_id}?error={result.message}",
            status_code=303,
        )

    return RedirectResponse(
    url=f"/rooms/{authoritative_room_id}?success=booking_updated",
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

    result = booking_service.delete_booking(
        db,
        booking,
    )

    if not result.success:
        return RedirectResponse(
            url=f"/rooms/{room_id}?error={result.message}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/rooms/{room_id}?success=booking_deleted",
        status_code=303,
    )
