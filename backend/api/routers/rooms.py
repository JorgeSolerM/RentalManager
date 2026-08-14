from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.database.session import SessionLocal
from backend.models.room import Room
from backend.services.booking_service import BookingService
from backend.services.platform_service import PlatformService
from backend.services.property_service import PropertyService
from backend.services.room_service import RoomService

router = APIRouter(prefix="/rooms")

templates = Jinja2Templates(directory="backend/templates")

property_service = PropertyService()
room_service = RoomService()
booking_service = BookingService()
platform_service = PlatformService()


@router.get("/property/{property_id}")
def list_rooms(
    request: Request,
    property_id: int,
):

    db = SessionLocal()

    try:

        property_obj = property_service.get_by_id(
            db,
            property_id,
        )

        if property_obj is None:

            raise HTTPException(
                status_code=404,
                detail="Propiedad no encontrada.",
            )

        rooms = room_service.list_rooms_by_property(
            db,
            property_id,
        )

        return templates.TemplateResponse(
            request=request,
            name="pages/rooms.html",
            context={
                "request": request,
                "current_page": "rooms",
                "property": property_obj,
                "rooms": rooms,
            },
        )

    finally:

        db.close()


@router.get("/edit/{room_id}")
def get_room(
    room_id: int,
):

    db = SessionLocal()

    try:

        room = room_service.get_room(
            db,
            room_id,
        )

        if room is None:

            raise HTTPException(
                status_code=404,
                detail="Habitación no encontrada.",
            )

        return {
            "id": room.id,
            "property_id": room.property_id,
            "code": room.code,
            "base_price": room.base_price,
            "square_meters": room.square_meters,
            "active": room.active,
        }

    finally:

        db.close()


@router.get("/{room_id}")
def room_workspace(
    request: Request,
    room_id: int,
):

    db = SessionLocal()

    try:

        room = room_service.get_room(
            db,
            room_id,
        )

        if room is None:

            raise HTTPException(
                status_code=404,
                detail="Habitación no encontrada.",
            )

        property_obj = property_service.get_by_id(
            db,
            room.property_id,
        )

        current_booking = booking_service.get_current_booking(
            db,
            room_id,
        )

        future_bookings = booking_service.get_future_bookings(
            db,
            room_id,
        )

        platforms = platform_service.list_platforms(
            db,
        )

        return templates.TemplateResponse(
            request=request,
            name="pages/room_workspace.html",
            context={
                "request": request,
                "current_page": "rooms",
                "room": room,
                "property": property_obj,
                "current_booking": current_booking,
                "future_bookings": future_bookings,
                "platforms": platforms,
            },
        )

    finally:

        db.close()


@router.post("/create")
def create_room(
    property_id: int = Form(...),
    code: str = Form(...),
    base_price: float = Form(...),
    square_meters: float | None = Form(None),
):

    db = SessionLocal()

    try:

        room = Room(
            property_id=property_id,
            code=code,
            display_order=1,
            base_price=base_price,
            square_meters=square_meters,
            active=True,
        )

        result = room_service.create_room(
            db,
            room,
        )

    finally:

        db.close()

    if result.success:

        return RedirectResponse(
            url=f"/rooms/property/{property_id}?success=room_created",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/rooms/property/{property_id}?error={result.message}",
        status_code=303,
    )


@router.post("/update/{room_id}")
def update_room(
    room_id: int,
    property_id: int = Form(...),
    code: str = Form(...),
    base_price: float = Form(...),
    square_meters: float | None = Form(None),
):

    db = SessionLocal()

    try:

        room = room_service.get_room(
            db,
            room_id,
        )

        if room is None:

            raise HTTPException(
                status_code=404,
                detail="Habitación no encontrada.",
            )

        room.code = code
        room.base_price = base_price
        room.square_meters = square_meters

        result = room_service.update_room(
            db,
            room,
        )

    finally:

        db.close()

    if result.success:

        return RedirectResponse(
            url=f"/rooms/property/{property_id}?success=room_updated",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/rooms/property/{property_id}?error={result.message}",
        status_code=303,
    )


@router.post("/delete/{room_id}")
def delete_room(
    room_id: int,
    property_id: int = Form(...),
):

    db = SessionLocal()

    try:

        room = room_service.get_room(
            db,
            room_id,
        )

        if room is None:

            raise HTTPException(
                status_code=404,
                detail="Habitación no encontrada.",
            )

        result = room_service.delete_room(
            db,
            room,
        )

    finally:

        db.close()

    if result.success:

        return RedirectResponse(
            url=f"/rooms/property/{property_id}?success=room_deleted",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/rooms/property/{property_id}?error={result.message}",
        status_code=303,
    )
