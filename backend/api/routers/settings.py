from fastapi import APIRouter, Depends, Request, UploadFile, File
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.core.config import APP_VERSION
from backend.services.platform_service import PlatformService
from backend.services.feature_service import FeatureService
from backend.services.manager_service import ManagerService
from backend.services.photo_service import UploadPayload
from backend.services.rental_requirement_service import RentalRequirementService

from fastapi import Form
from fastapi.responses import RedirectResponse

from backend.models.platform import Platform




router = APIRouter(prefix="/settings")

templates = Jinja2Templates(directory="backend/templates")

platform_service = PlatformService()
feature_service = FeatureService()
manager_service = ManagerService()
requirement_service = RentalRequirementService()

@router.get("/")
def settings(request: Request, db: Session = Depends(get_db)):

    return templates.TemplateResponse(
        request=request,
        name="pages/settings.html",
        context={
            "request": request,
            "current_page": "settings",
            "settings_section": "general",
        },
    )

@router.get("/features")
def features(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request=request, name="pages/settings_features.html", context={"request": request, "current_page": "settings", "settings_section": "features", "features": feature_service.list_all(db)})

@router.get("/system")
def system(request: Request):
    return templates.TemplateResponse(request=request, name="pages/settings_system.html", context={"request": request, "current_page": "settings", "settings_section": "system", "version": APP_VERSION})

@router.get("/managers")
def managers(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(request=request, name="pages/settings_managers.html", context={"request": request, "current_page": "settings", "settings_section": "managers", "managers": manager_service.list_all(db)})

@router.get("/requirements")
def requirements(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="pages/settings_requirements.html",
        context={
            "request": request,
            "current_page": "settings",
            "settings_section": "requirements",
            "requirements": requirement_service.list_all(db),
        },
    )

@router.post("/requirements/create")
def create_requirement(public_name: str = Form(...), slug: str = Form(...), public_description: str = Form(""), display_order: int = Form(0), active: bool = Form(False), db: Session = Depends(get_db)):
    result = requirement_service.save(db, None, public_name=public_name, slug=slug, public_description=public_description, display_order=display_order, active=active)
    return RedirectResponse(f"/settings/requirements?{'success=requirement_saved' if result.success else 'error='+result.message}", 303)

@router.post("/requirements/update/{requirement_id}")
def update_requirement(requirement_id: int, public_name: str = Form(...), slug: str = Form(...), public_description: str = Form(""), display_order: int = Form(0), active: bool = Form(False), db: Session = Depends(get_db)):
    result = requirement_service.save(db, requirement_id, public_name=public_name, slug=slug, public_description=public_description, display_order=display_order, active=active)
    return RedirectResponse(f"/settings/requirements?{'success=requirement_saved' if result.success else 'error='+result.message}", 303)

@router.post("/requirements/delete/{requirement_id}")
def delete_requirement(requirement_id: int, db: Session = Depends(get_db)):
    result = requirement_service.delete(db, requirement_id)
    return RedirectResponse(f"/settings/requirements?{'success=requirement_deleted' if result.success else 'error='+result.message}", 303)

@router.get("/platforms")
def platforms(
    request: Request,
    db: Session = Depends(get_db),
):

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
            "settings_section": "platforms",
        },
    )


@router.post("/features/create")
def create_feature(name: str = Form(...), slug: str = Form(...), scope: str = Form(...), category: str = Form(...), icon_key: str = Form(""), display_order: int = Form(0), active: bool = Form(False), db: Session = Depends(get_db)):
    result = feature_service.save(db, None, name=name, slug=slug, scope=scope, category=category, icon_key=icon_key, display_order=display_order, active=active)
    return RedirectResponse(f"/settings/features?{'success=feature_saved' if result.success else 'error='+result.message}", 303)


@router.post("/features/update/{feature_id}")
def update_feature(feature_id: int, name: str = Form(...), slug: str = Form(...), scope: str = Form(...), category: str = Form(...), icon_key: str = Form(""), display_order: int = Form(0), active: bool = Form(False), db: Session = Depends(get_db)):
    result = feature_service.save(db, feature_id, name=name, slug=slug, scope=scope, category=category, icon_key=icon_key, display_order=display_order, active=active)
    return RedirectResponse(f"/settings/features?{'success=feature_saved' if result.success else 'error='+result.message}", 303)


@router.post("/features/delete/{feature_id}")
def delete_feature(feature_id: int, db: Session = Depends(get_db)):
    result = feature_service.delete(db, feature_id)
    return RedirectResponse(f"/settings/features?{'success=feature_deleted' if result.success else 'error='+result.message}", 303)

@router.post("/managers/create")
def create_manager(name: str = Form(...), phone: str = Form(""), active: bool = Form(False), db: Session = Depends(get_db)):
    result = manager_service.save(db, None, name=name, phone=phone, active=active)
    return RedirectResponse(f"/settings/managers?{'success=manager_saved' if result.success else 'error='+result.message}", 303)

@router.post("/managers/update/{manager_id}")
def update_manager(manager_id: int, name: str = Form(...), phone: str = Form(""), active: bool = Form(False), db: Session = Depends(get_db)):
    result = manager_service.save(db, manager_id, name=name, phone=phone, active=active)
    return RedirectResponse(f"/settings/managers?{'success=manager_saved' if result.success else 'error='+result.message}", 303)

@router.post("/managers/{manager_id}/assign-unassigned")
def assign_unassigned(manager_id: int, db: Session = Depends(get_db)):
    result = manager_service.assign_unassigned(db, manager_id)
    return RedirectResponse(f"/settings/managers?{'success=manager_assigned' if result.success else 'error='+result.message}", 303)

@router.post("/managers/{manager_id}/photo")
async def upload_manager_photo(manager_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    result = manager_service.upload_photo(db, manager_id, UploadPayload(await file.read(), file.content_type))
    return RedirectResponse(f"/settings/managers?{'success=manager_photo_saved' if result.success else 'error='+result.message}", 303)

@router.post("/platforms/create")
def create_platform(

    name: str = Form(...),

    slug: str = Form(...),

    supports_import: bool = Form(False),

    supports_export: bool = Form(False),
    db: Session = Depends(get_db),

):

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
    db: Session = Depends(get_db),
):

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


@router.post("/platforms/update/{platform_id}")
def update_platform(

    platform_id: int,

    name: str = Form(...),

    slug: str = Form(...),

    supports_import: bool = Form(False),

    supports_export: bool = Form(False),
    db: Session = Depends(get_db),

):

    result = platform_service.update_platform(
        db,
        platform_id,
        name,
        slug,
        supports_import,
        supports_export,
    )

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
    db: Session = Depends(get_db),

):

    result = platform_service.delete_platform(
        db,
        platform_id,
    )

    if not result.success:

        return RedirectResponse(
            url=f"/settings/platforms?error={result.message}",
            status_code=303,
        )

    return RedirectResponse(
        url="/settings/platforms?success=platform_deleted",
        status_code=303,
    )
