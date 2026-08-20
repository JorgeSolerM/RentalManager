from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.models.property import Property
from backend.services.property_service import PropertyService
from backend.services.room_service import RoomService
from backend.services.photo_service import PhotoService
from backend.services.commercial_publication_service import CommercialPublicationService, REASON_MESSAGES

router = APIRouter(prefix="/properties")

templates = Jinja2Templates(directory="backend/templates")

property_service = PropertyService()
room_service = RoomService()
photo_service = PhotoService()
commercial_service = CommercialPublicationService()


@router.get("/")
def list_properties(
    request: Request,
    db: Session = Depends(get_db),
):

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
            "current_page": "properties",
            "properties": properties_data,
        },
    )


@router.get("/{property_id}")
def get_property(
    property_id: int,
    db: Session = Depends(get_db),
):

    property_obj = property_service.get_by_id(db, property_id)

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


@router.get("/{property_id}/photos")
def property_photos(request: Request, property_id: int, db: Session = Depends(get_db)):
    property_obj = property_service.get_by_id(db, property_id)
    if property_obj is None:
        raise HTTPException(status_code=404, detail="Propiedad no encontrada.")
    return templates.TemplateResponse(
        request=request,
        name="pages/property_photos.html",
        context={
            "request": request,
            "current_page": "properties",
            "property": property_obj,
            "photo_gallery": photo_service.property_gallery(db, property_id),
        },
    )


@router.get("/{property_id}/publication")
def property_publication(request: Request, property_id: int, db: Session = Depends(get_db)):
    obj = property_service.get_by_id(db, property_id)
    if obj is None: raise HTTPException(404)
    reasons = commercial_service.property_reasons(obj)
    return templates.TemplateResponse(request=request, name="pages/property_publication.html", context={
        "request": request, "current_page": "properties", "property": obj,
        "features": commercial_service.feature_options(db, obj), "reasons": reasons,
        "reason_messages": REASON_MESSAGES,
    })


@router.post("/{property_id}/publication")
def save_property_publication(property_id: int, public_title: str = Form(""), public_location: str = Form(""), public_slug: str = Form(""), is_published: bool = Form(False), feature_ids: list[int] = Form([]), db: Session = Depends(get_db)):
    result = commercial_service.update_property(db, property_id, title=public_title, location=public_location, slug=public_slug, is_published=is_published, feature_ids=feature_ids)
    key = "success=publication_saved" if result.success else f"error={result.message}"
    return RedirectResponse(f"/properties/{property_id}/publication?{key}", status_code=303)


@router.post("/create")
def create_property(
    name: str = Form(...),
    alias: str = Form(""),
    address: str = Form(...),
    city: str = Form(...),
    owner: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):

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
def toggle_property(
    property_id: int,
    db: Session = Depends(get_db),
):

    result = property_service.toggle_property(db, property_id)

    if not result.success and result.message == "not_found":

        raise HTTPException(
            status_code=404,
            detail="Propiedad no encontrada.",
        )

    return {
        "success": True,
        "active": result.data.active,
    }


@router.post("/update/{property_id}")
def update_property(
    property_id: int,
    name: str = Form(...),
    alias: str = Form(""),
    address: str = Form(...),
    city: str = Form(...),
    owner: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):

    result = property_service.update_property(
        db, property_id, name, alias or None, address, city, owner, notes or None
    )

    if not result.success and result.message == "not_found":
        raise HTTPException(status_code=404, detail="Propiedad no encontrada.")

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
    db: Session = Depends(get_db),
):

    result = property_service.delete_property(db, property_id)

    if not result.success and result.message == "not_found":
        raise HTTPException(status_code=404, detail="Propiedad no encontrada.")

    if result.success:

        return RedirectResponse(
            url="/properties/?success=property_deleted",
            status_code=303,
        )

    return RedirectResponse(
        url=f"/properties/?error={result.message}",
        status_code=303,
    )
