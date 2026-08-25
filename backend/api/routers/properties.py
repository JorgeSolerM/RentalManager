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
from backend.services.manager_service import ManagerService
from backend.services.property_rules_service import PropertyRulesService

router = APIRouter(prefix="/properties")

templates = Jinja2Templates(directory="backend/templates")

property_service = PropertyService()
room_service = RoomService()
photo_service = PhotoService()
commercial_service = CommercialPublicationService()
manager_service = ManagerService()
property_rules_service = PropertyRulesService()


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
        "street": property_obj.street,
        "street_number": property_obj.street_number,
        "floor": property_obj.floor,
        "door": property_obj.door,
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
        "managers": manager_service.active_options(db, obj.manager_id),
        "reason_messages": REASON_MESSAGES,
    })


@router.post("/{property_id}/publication")
def save_property_publication(property_id: int, public_title: str = Form(""), public_location: str = Form(""), public_slug: str = Form(""), shared_full_bathroom_count: str = Form(""), shared_toilet_count: str = Form(""), is_published: bool = Form(False), feature_ids: list[int] = Form([]), manager_id: int | None = Form(None), db: Session = Depends(get_db)):
    result = commercial_service.update_property(db, property_id, title=public_title, location=public_location, slug=public_slug, shared_full_bathroom_count=shared_full_bathroom_count, shared_toilet_count=shared_toilet_count, is_published=is_published, feature_ids=feature_ids, manager_id=manager_id)
    key = "success=publication_saved" if result.success else f"error={result.message}"
    return RedirectResponse(f"/properties/{property_id}/publication?{key}", status_code=303)


@router.get("/{property_id}/publication/rules")
def property_publication_rules(
    request: Request, property_id: int, db: Session = Depends(get_db)
):
    obj = property_rules_service.get(db, property_id)
    if obj is None:
        raise HTTPException(404)
    return templates.TemplateResponse(
        request=request,
        name="pages/property_publication_rules.html",
        context={
            "request": request,
            "current_page": "properties",
            "property": obj,
            "requirements": property_rules_service.requirement_options(db, obj),
            "selected_requirement_ids": {item.id for item in obj.requirements},
            "publication_section": "rules",
        },
    )


@router.post("/{property_id}/publication/rules")
def save_property_publication_rules(
    property_id: int,
    smoking_allowed: str = Form("unknown"),
    pets_allowed: str = Form("unknown"),
    musical_instruments_allowed: str = Form("unknown"),
    minimum_tenant_age: str = Form(""),
    maximum_tenant_age: str = Form(""),
    requirement_ids: list[int] = Form([]),
    db: Session = Depends(get_db),
):
    result = property_rules_service.update(
        db,
        property_id,
        smoking_allowed=smoking_allowed,
        pets_allowed=pets_allowed,
        musical_instruments_allowed=musical_instruments_allowed,
        minimum_tenant_age=minimum_tenant_age,
        maximum_tenant_age=maximum_tenant_age,
        requirement_ids=requirement_ids,
    )
    key = "success=property_rules_saved" if result.success else f"error={result.message}"
    return RedirectResponse(
        f"/properties/{property_id}/publication/rules?{key}", status_code=303
    )


@router.post("/create")
def create_property(
    name: str = Form(...),
    alias: str = Form(""),
    street: str = Form(...),
    street_number: str = Form(""),
    floor: str = Form(""),
    door: str = Form(""),
    city: str = Form(...),
    owner: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):

    property_obj = Property(
        name=name,
        alias=alias or None,
        address="",
        street=street,
        street_number=street_number or None,
        floor=floor or None,
        door=door or None,
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
    street: str = Form(...),
    street_number: str = Form(""),
    floor: str = Form(""),
    door: str = Form(""),
    city: str = Form(...),
    owner: str = Form(...),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):

    result = property_service.update_property(
        db, property_id, name, alias or None, street, street_number or None,
        floor or None, door or None, city, owner, notes or None
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
