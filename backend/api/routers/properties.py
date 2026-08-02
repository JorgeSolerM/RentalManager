from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.database.session import SessionLocal
from backend.models.property import Property
from backend.services.property_service import PropertyService

router = APIRouter(prefix="/properties")

templates = Jinja2Templates(directory="backend/templates")

property_service = PropertyService()


@router.get("/")
def list_properties(request: Request):

    db = SessionLocal()

    try:

        properties = property_service.list_properties(db)

        return templates.TemplateResponse(
            request=request,
            name="pages/properties.html",
            context={
                "request": request,
                "version": "1.0.0",
                "current_page": "properties",
                "properties": properties,
            },
        )

    finally:

        db.close()


@router.get("/{property_id}")
def get_property(property_id: int):

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

        property_service.create_property(
            db,
            property_obj,
        )

    finally:

        db.close()

    return RedirectResponse(
        url="/properties/",
        status_code=303,
    )


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

        property_obj = property_service.get_property(
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

        property_service.update_property(
            db,
            property_obj,
        )

    finally:

        db.close()

    return RedirectResponse(
        url="/properties/",
        status_code=303,
    )
