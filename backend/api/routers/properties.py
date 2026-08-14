from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.database.session import SessionLocal
from backend.models.property import Property
from backend.services.property_service import PropertyService
from backend.services.room_service import RoomService

router = APIRouter(prefix="/properties")

templates = Jinja2Templates(directory="backend/templates")

property_service = PropertyService()
room_service = RoomService()


@router.get("/")
def list_properties(request: Request):

    db = SessionLocal()

    try:

        properties = property_service.list_properties(db)

        properties_data = []

        for property_obj in properties:

            room_count = room_service.count_rooms_by_property(
                db,
                property_obj.id,
            )

            properties_data.append(
                {
                    "property": property_obj,
                    "room_count": room_count,
                }
            )

        return templates.TemplateResponse(
            request=request,
            name="pages/properties.html",
            context={
                "request": request,
                "version": "1.0.0",
                "current_page": "properties",
                "properties": properties_data,
            },
        )

    finally:

        db.close()


@router.get("/{property_id}")
def get_property(property_id: int):

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

        return {
            "id": property_obj.id,
            "name": property_obj.name,
            "alias": property_obj.alias,
            "address": property_obj.address,
            "city": property_obj.city,
            "owner": property_obj.owner,
            "notes": property_obj.notes,
            "active": property_obj.active,
        }

    finally:

        db.close()


@router.post("/create")
def create_property(
    name: str = Form(...),
    alias: str = Form(""),
    address: str = Form(...),
    city: str = Form(...),
    owner: str = Form(...),
    notes: str = Form(""),
):

    db = SessionLocal()

    try:

        property_obj = Property(
            name=name,
            alias=alias or None,
            address=address,
            city=city,
            owner=owner,
            notes=notes or None,
            active=True,
        )

        result = property_service.create_property(
            db,
            property_obj,
        )

    finally:

        db.close()

    if result.success:

        return RedirectResponse(
            url="/properties/?success=property_updated",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/properties/?error={result.message}",
        status_code=303,
    )


@router.post("/toggle/{property_id}")
def toggle_property(property_id: int):

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

        property_obj = property_service.toggle_property(
            db,
            property_obj,
        )

        return {
            "success": True,
            "active": property_obj.active,
        }

    finally:

        db.close()


@router.post("/update/{property_id}")
def update_property(
    property_id: int,
    name: str = Form(...),
    alias: str = Form(""),
    address: str = Form(...),
    city: str = Form(...),
    owner: str = Form(...),
    notes: str = Form(""),
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

        property_obj.name = name
        property_obj.alias = alias or None
        property_obj.address = address
        property_obj.city = city
        property_obj.owner = owner
        property_obj.notes = notes or None

        result = property_service.update_property(
            db,
            property_obj,
        )

    finally:

        db.close()

    if result.success:

        return RedirectResponse(
            url="/properties/?success=property_updated",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/properties/?error={result.message}",
        status_code=303,
    )
@router.post("/delete/{property_id}")
def delete_property(
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

        result = property_service.delete_property(
            db,
            property_obj,
        )

    finally:

        db.close()

    if result.success:

        return RedirectResponse(
            url="/properties/?success=property_deleted",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/properties/?error={result.message}",
        status_code=303,
    )
