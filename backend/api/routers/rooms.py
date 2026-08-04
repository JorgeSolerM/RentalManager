from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.database.session import SessionLocal
from backend.models.room import Room
from backend.services.property_service import PropertyService
from backend.services.room_service import RoomService

router = APIRouter(prefix="/rooms")

templates = Jinja2Templates(directory="backend/templates")

property_service = PropertyService()
room_service = RoomService()


@router.get("/property/{property_id}")
def list_rooms(
    request: Request,
    property_id: int,
):

    db = SessionLocal()

    try:

        property_obj = property_service.get_property(
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

        room_service.create_room(
            db,
            room,
        )

    finally:

        db.close()

    return RedirectResponse(
        url=f"/rooms/property/{property_id}",
        status_code=303,
    )
