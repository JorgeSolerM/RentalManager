from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from backend.database.session import SessionLocal
from backend.services.platform_service import PlatformService

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


