from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.schemas.booking_schema import BookingResponse
from backend.services.booking_service import BookingService
from backend.services.booking_party_service import BookingPartyService

router = APIRouter(prefix="/bookings")

booking_service = BookingService()
party_service = BookingPartyService()


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

        guest_name=(
            None
            if booking.operational_person_name == "Huésped desconocido"
            else booking.operational_person_name
        ),
        source_guest_name=booking.source_guest_name,
        parties=[
            {"id": party.id, "person_id": party.person_id, "person_name": party.person.display_name or party.person.full_name, "role": party.role}
            for party in booking.parties
        ],

        origin=booking.origin,

        check_in=booking.check_in,

        check_out=booking.check_out,

        expected_arrival_date=booking.expected_arrival_date,

        expected_departure_date=booking.expected_departure_date,

        price=booking.price,

        notes=booking.notes,

        editable=booking_service.is_manual_booking(booking),

        external_block_deletable=booking_service.can_delete_imported_block(booking),

    )


@router.post("/create")
def create_booking(

    room_id: int = Form(...),

    guest_name: str = Form(...),

    check_in: date = Form(...),

    check_out: date = Form(...),

    price: float | None = Form(None),

    notes: str | None = Form(None),

    expected_arrival_date: date | None = Form(None),

    expected_departure_date: date | None = Form(None),
    db: Session = Depends(get_db),

):

    result = booking_service.create_manual_booking(
        db,
        room_id,
        guest_name,
        check_in,
        check_out,
        price,
        notes,
        expected_arrival_date,
        expected_departure_date,
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

    check_in: date = Form(...),

    check_out: date = Form(...),

    price: float | None = Form(None),

    notes: str | None = Form(None),

    expected_arrival_date: date | None = Form(None),

    expected_departure_date: date | None = Form(None),
    db: Session = Depends(get_db),

):

    result = booking_service.update_manual_booking(
        db,
        booking_id,
        check_in,
        check_out,
        price,
        notes,
        expected_arrival_date,
        expected_departure_date,
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
        url=f"/rooms/{room_id}?success={result.message}",
        status_code=303,
    )


@router.post("/update-imported-local/{booking_id}")
def update_imported_local_details(
    booking_id: int,
    expected_arrival_date: date | None = Form(None),
    expected_departure_date: date | None = Form(None),
    db: Session = Depends(get_db),
):
    result = booking_service.update_imported_local_details(
        db,
        booking_id,
        expected_arrival_date,
        expected_departure_date,
    )

    if not result.success and result.message == "not_found":
        raise HTTPException(status_code=404, detail="Reserva no encontrada.")

    room_id = result.data.room_id
    if not result.success:
        return RedirectResponse(
            url=f"/rooms/{room_id}?error={result.message}",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/rooms/{room_id}?success=booking_local_details_updated",
        status_code=303,
    )


@router.post("/{booking_id}/parties")
def add_booking_party(booking_id: int, person_id: int = Form(...), role: str = Form(...), db: Session = Depends(get_db)):
    result = party_service.add(db, booking_id, person_id, role)
    if not result.success:
        raise HTTPException(422, detail=result.message)
    party = result.data
    return {"id": party.id, "person_id": party.person_id, "person_name": party.person.display_name or party.person.full_name, "role": party.role}


@router.post("/{booking_id}/parties/{party_id}/remove")
def remove_booking_party(booking_id: int, party_id: int, db: Session = Depends(get_db)):
    result = party_service.remove(db, party_id, booking_id)
    if not result.success:
        raise HTTPException(422, detail=result.message)
    return {"success": True}
