from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from backend.database.session import SessionLocal
from backend.services.platform_service import PlatformService

from fastapi import Form
from fastapi.responses import RedirectResponse

from backend.models.platform import Platform




router = APIRouter(prefix="/settings")

templates = Jinja2Templates(directory="backend/templates")

platform_service = PlatformService()

@router.get("/")
def settings(request: Request):

    return templates.TemplateResponse(
        request=request,
        name="pages/settings.html",
        context={
            "request": request,
            "version": "1.0.0",
            "current_page": "settings",
        },
    )

@router.get("/platforms")
def platforms(
    request: Request,
):

    db = SessionLocal()

    try:

        platforms = platform_service.list_platforms(
            db,
        )

        print("QUERY:", request.url)

        return templates.TemplateResponse(
            request=request,
            name="pages/platforms.html",
            context={
                "request": request,
                "current_page": "settings",
                "platforms": platforms,
            },
        )

    finally:

        db.close()

@router.post("/platforms/create")
def create_platform(

    name: str = Form(...),

    slug: str = Form(...),

    supports_import: bool = Form(False),

    supports_export: bool = Form(False),

):

    db = SessionLocal()

    try:

        platform = Platform(

            name=name,

            slug=slug,

            supports_import=supports_import,

            supports_export=supports_export,

            active=True,

        )

        platform_service.create_platform(
            db,
            platform,
        )

    finally:

        db.close()

    return RedirectResponse(
        url="/settings/platforms?success=platform_created",
        status_code=303,
    )
