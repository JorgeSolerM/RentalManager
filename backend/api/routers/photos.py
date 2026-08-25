from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
import re
from sqlalchemy.orm import Session

from backend.core.media_storage import MAX_IMAGE_UPLOAD_BYTES, PUBLIC_IMAGE_WIDTHS
from backend.database.session import get_db
from backend.services.photo_service import PhotoService, UploadPayload
from backend.schemas.photo_schema import PhotoOrderRequest


router = APIRouter()
photo_service = PhotoService()
SAFE_RETURN_TO = re.compile(
    r"^/(?:properties/\d+/photos|rooms/\d+(?:/publication|\?tab=configuracion)?)$"
)


async def _payloads(files: list[UploadFile]) -> list[UploadPayload]:
    result = []
    for upload in files:
        content = await upload.read(MAX_IMAGE_UPLOAD_BYTES + 1)
        result.append(UploadPayload(content=content, content_type=upload.content_type))
        await upload.close()
    return result


def _redirect(url: str, result, success: str = "photos_updated"):
    key = "success" if result.success else "error"
    value = success if result.success else result.message
    separator = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{separator}{key}={value}", status_code=303)


def _validated_return_to(value: str) -> str:
    if not SAFE_RETURN_TO.fullmatch(value):
        raise HTTPException(status_code=400, detail="Destino de retorno no válido.")
    return value


@router.post("/properties/{property_id}/photos/upload")
async def upload_property_photos(property_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    result = photo_service.upload_property(db, property_id, await _payloads(files))
    return _redirect(f"/properties/{property_id}/photos", result, "photos_uploaded")


@router.post("/rooms/{room_id}/photos/upload")
async def upload_room_photos(
    room_id: int,
    files: list[UploadFile] = File(...),
    return_to: str = Form(""),
    db: Session = Depends(get_db),
):
    result = photo_service.upload_room(db, room_id, await _payloads(files))
    destination = (
        _validated_return_to(return_to)
        if return_to
        else f"/rooms/{room_id}?tab=configuracion"
    )
    return _redirect(destination, result, "photos_uploaded")


@router.post("/{owner_type}-photos/{photo_id}/primary")
def set_primary(owner_type: str, photo_id: int, return_to: str = Form(...), db: Session = Depends(get_db)):
    if owner_type not in {"property", "room"}:
        raise HTTPException(404)
    return _redirect(_validated_return_to(return_to), photo_service.set_primary(db, owner_type, photo_id), "photo_primary_updated")


@router.post("/{owner_type}-photos/{photo_id}/move")
def move_photo(owner_type: str, photo_id: int, direction: str = Form(...), return_to: str = Form(...), db: Session = Depends(get_db)):
    if owner_type not in {"property", "room"}:
        raise HTTPException(404)
    return _redirect(_validated_return_to(return_to), photo_service.reorder(db, owner_type, photo_id, direction), "photos_reordered")


@router.post("/{owner_type}-photos/{photo_id}/delete")
def delete_photo(owner_type: str, photo_id: int, return_to: str = Form(...), db: Session = Depends(get_db)):
    if owner_type not in {"property", "room"}:
        raise HTTPException(404)
    return _redirect(_validated_return_to(return_to), photo_service.delete_photo(db, owner_type, photo_id), "photo_deleted")


@router.post("/photo-order/{owner_type}")
def reorder_photo_gallery(
    owner_type: str,
    payload: PhotoOrderRequest,
    db: Session = Depends(get_db),
):
    result = photo_service.reorder_exact(
        db, owner_type, payload.owner_id, payload.photo_ids
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"success": True}


@router.get("/media-assets/{asset_id}/variants/{width}")
def admin_media_variant(asset_id: int, width: int, db: Session = Depends(get_db)):
    if width not in PUBLIC_IMAGE_WIDTHS:
        raise HTTPException(404)
    path = photo_service.variant_path(db, asset_id, width)
    if path is None:
        raise HTTPException(404)
    response = FileResponse(path, media_type="image/webp")
    response.headers["Cache-Control"] = "private, max-age=3600"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response
