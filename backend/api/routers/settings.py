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

        result = platform_service.create_platform(
            db,
            platform,
        )

        print(result)
        print(result.success)
        print(result.message)

    finally:

        db.close()

    if not result.success:

        return RedirectResponse(
            url=f"/settings/platforms?error={result.message}",
            status_code=303,
        )

    return RedirectResponse(
        url="/settings/platforms?success=platform_created",
        status_code=303,
    )


@router.get("/platforms/edit/{platform_id}")
def get_platform(
    platform_id: int,
):

    db = SessionLocal()

    try:

        platform = platform_service.get_by_id(
            db,
            platform_id,
        )

        return {

            "id": platform.id,

            "name": platform.name,

            "slug": platform.slug,

            "supports_import": platform.supports_import,

            "supports_export": platform.supports_export,

            "active": platform.active,

        }

    finally:

        db.close()


@router.post("/platforms/update/{platform_id}")
def update_platform(

    platform_id: int,

    name: str = Form(...),

    slug: str = Form(...),

    supports_import: bool = Form(False),

    supports_export: bool = Form(False),

):

    db = SessionLocal()

    try:

        result = platform_service.update_platform(
            db,
            platform_id,
            name,
            slug,
            supports_import,
            supports_export,
        )

    finally:

        db.close()

    if not result.success:

        return RedirectResponse(
            url=f"/settings/platforms?error={result.message}",
            status_code=303,
        )

    return RedirectResponse(
        url="/settings/platforms?success=platform_updated",
        status_code=303,
    )



@router.post("/platforms/delete/{platform_id}")
def delete_platform(

    platform_id: int,

):

    db = SessionLocal()

    try:

        result = platform_service.delete_platform(
            db,
            platform_id,
        )

    finally:

        db.close()

    if not result.success:

        return RedirectResponse(
            url=f"/settings/platforms?error={result.message}",
            status_code=303,
        )

    return RedirectResponse(
        url="/settings/platforms?success=platform_deleted",
        status_code=303,
    )
