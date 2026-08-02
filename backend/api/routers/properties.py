from fastapi import APIRouter, Form, Request
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

        property_service.create_property(db, property_obj)

    finally:
        db.close()

    return RedirectResponse(
        url="/properties/",
        status_code=303,
    )
