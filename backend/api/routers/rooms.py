from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.models.room import Room
from backend.services.booking_service import BookingService
from backend.services.property_service import PropertyService
from backend.services.room_calendar_service import RoomCalendarService
from backend.services.master_calendar_service import MasterCalendarService
from backend.services.room_service import RoomService
from backend.services.photo_service import PhotoService
from backend.services.commercial_publication_service import CommercialPublicationService, REASON_MESSAGES

router = APIRouter(prefix="/rooms")

templates = Jinja2Templates(directory="backend/templates")

property_service = PropertyService()
room_service = RoomService()
booking_service = BookingService()
room_calendar_service = RoomCalendarService()
master_calendar_service = MasterCalendarService()
photo_service = PhotoService()
commercial_service = CommercialPublicationService()


@router.get("/property/{property_id}")
def list_rooms(
    request: Request,
    property_id: int,
    db: Session = Depends(get_db),
):

    property_obj = property_service.get_by_id(
        db,
        property_id,
    )

    if property_obj is None:

        raise HTTPException(
            status_code=404,
            detail="Propiedad no encontrada.",
        )

    rooms = room_service.list_rooms_with_platform_status(
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


@router.get("/edit/{room_id}")
def get_room(
    room_id: int,
    db: Session = Depends(get_db),
):

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


@router.get("/{room_id}")
def room_workspace(
    request: Request,
    room_id: int,
    db: Session = Depends(get_db),
):

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

    calendar_configurations = room_calendar_service.list_configurations(db, room_id)
    master_calendar_views = master_calendar_service.list_public_views(db, room)
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
            "calendar_configurations": calendar_configurations,
            "master_calendar_views": master_calendar_views,
        },
    )


@router.get("/{room_id}/publication")
def room_publication(request: Request, room_id: int, db: Session = Depends(get_db)):
    room = room_service.get_room(db, room_id)
    if room is None: raise HTTPException(404)
    property_obj = property_service.get_by_id(db, room.property_id)
    property_gallery = photo_service.property_gallery(db, property_obj.id)
    room_gallery = photo_service.room_gallery(db, room_id)
    public_slug_preview = commercial_service.room_slug_preview(db, room)
    return templates.TemplateResponse(request=request, name="pages/room_publication.html", context={
        "request": request, "current_page": "rooms", "room": room,
        "property": property_obj,
        "features": commercial_service.feature_options(db, room),
        "public_slug_preview": public_slug_preview,
        "inherited_features": property_obj.features,
        "inherited_photo_count": len(property_gallery),
        "photo_gallery": room_gallery,
        "highlight_options": commercial_service.highlight_options(room),
        "selected_highlight_ids": {highlight.feature_id for highlight in room.public_highlights},
        "copy_source_rooms": commercial_service.copy_source_options(db, room),
        "assessment": commercial_service.publication.assess_room(
            db, room_id, public_slug_candidate=public_slug_preview
        ),
        "reason_messages": REASON_MESSAGES,
    })


@router.post("/{room_id}/publication")
def save_room_publication(room_id: int, public_title: str = Form(""), public_description: str = Form(""), base_price: str = Form(""), square_meters: str = Form(""), minimum_stay_months: str = Form(""), maximum_stay_months: str = Form(""), tenant_gender_preference: str = Form("any"), is_published: bool = Form(False), feature_ids: list[int] = Form([]), highlight_feature_ids: list[int] = Form([]), db: Session = Depends(get_db)):
    result = commercial_service.update_room(db, room_id, title=public_title, description=public_description, base_price=base_price, square_meters=square_meters, minimum_stay_months=minimum_stay_months, maximum_stay_months=maximum_stay_months, tenant_gender_preference=tenant_gender_preference, is_published=is_published, feature_ids=feature_ids, highlight_feature_ids=highlight_feature_ids)
    key = "success=publication_saved" if result.success else f"error={result.message}"
    return RedirectResponse(f"/rooms/{room_id}/publication?{key}", status_code=303)


@router.post("/{room_id}/publication/copy-configuration")
def copy_room_publication_configuration(
    room_id: int,
    source_room_id: int = Form(...),
    db: Session = Depends(get_db),
):
    result = commercial_service.copy_room_configuration(db, room_id, source_room_id)
    if not result.success:
        return RedirectResponse(
            f"/rooms/{room_id}/publication?error={result.message}", status_code=303
        )
    data = result.data
    omitted = data["inactive_features_omitted"] + data["highlights_omitted"]
    return RedirectResponse(
        f"/rooms/{room_id}/publication?success=room_configuration_copied"
        f"&source={data['source_code']}&omitted={omitted}",
        status_code=303,
    )


@router.post("/create")
def create_room(
    property_id: int = Form(...),
    code: str = Form(...),
    db: Session = Depends(get_db),
):

    room = Room(
        property_id=property_id,
        code=code,
        display_order=1,
        base_price=None,
        square_meters=None,
        active=True,
    )

    result = room_service.create_room(
        db,
        room,
    )

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
    db: Session = Depends(get_db),
):

    result = room_service.update_room(
        db, room_id, code
    )

    if not result.success and result.message == "not_found":
        raise HTTPException(status_code=404, detail="Habitación no encontrada.")

    if result.success:

        return RedirectResponse(
            url=f"/rooms/property/{property_id}?success=room_updated",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/rooms/property/{property_id}?error={result.message}",
        status_code=303,
    )


def _room_lifecycle_redirect(room: Room, destination: str, outcome: str) -> str:
    if destination == "workspace":
        return f"/rooms/{room.id}?{outcome}"
    return f"/rooms/property/{room.property_id}?{outcome}"


@router.post("/{room_id}/archive")
def archive_room(
    room_id: int,
    destination: str = Form("list"),
    db: Session = Depends(get_db),
):
    result = room_service.archive(db, room_id)
    if not result.success and result.message == "not_found":
        raise HTTPException(status_code=404, detail="Habitación no encontrada.")
    room = result.data or room_service.get_room(db, room_id)
    outcome = (
        "success=room_archived"
        if result.success
        else f"error={result.message}"
    )
    return RedirectResponse(
        _room_lifecycle_redirect(room, destination, outcome), status_code=303
    )


@router.post("/{room_id}/restore")
def restore_room(
    room_id: int,
    destination: str = Form("list"),
    db: Session = Depends(get_db),
):
    result = room_service.restore(db, room_id)
    if not result.success and result.message == "not_found":
        raise HTTPException(status_code=404, detail="Habitación no encontrada.")
    return RedirectResponse(
        _room_lifecycle_redirect(
            result.data, destination, "success=room_restored"
        ),
        status_code=303,
    )


@router.post("/{room_id}/put-into-operation")
def put_room_into_operation(
    room_id: int,
    destination: str = Form("list"),
    db: Session = Depends(get_db),
):
    result = room_service.put_into_operation(db, room_id)
    if not result.success and result.message == "not_found":
        raise HTTPException(status_code=404, detail="Habitación no encontrada.")
    room = result.data or room_service.get_room(db, room_id)
    outcome = (
        "success=room_put_into_operation"
        if result.success
        else f"error={result.message}"
    )
    return RedirectResponse(
        _room_lifecycle_redirect(room, destination, outcome), status_code=303
    )


@router.post("/delete/{room_id}")
def delete_room(
    room_id: int,
    property_id: int = Form(...),
    db: Session = Depends(get_db),
):

    result = room_service.delete_room(db, room_id)

    if not result.success and result.message == "not_found":
        raise HTTPException(status_code=404, detail="Habitación no encontrada.")

    if result.success:

        return RedirectResponse(
            url=f"/rooms/property/{property_id}?success=room_deleted",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/rooms/property/{property_id}?error={result.message}",
        status_code=303,
    )
