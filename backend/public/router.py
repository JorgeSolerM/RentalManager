import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.core.config import get_public_site_base_url, get_public_site_name
from backend.core.media_storage import PUBLIC_IMAGE_WIDTHS, MediaFileStore
from backend.models.media_asset import MediaAsset
from backend.public.database import get_public_db
from backend.public.service import PublicRoomService


router = APIRouter()
templates = Jinja2Templates(directory="backend/public/templates")
STORAGE_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}$")


@router.api_route("/", methods=["GET", "HEAD"], name="public_catalog")
def public_catalog(request: Request, db: Session = Depends(get_public_db)):
    rooms = PublicRoomService().list_rooms(db)
    return templates.TemplateResponse(
        request=request,
        name="catalog.html",
        context={
            "request": request,
            "site_name": get_public_site_name(),
            "rooms": rooms,
            "base_url": get_public_site_base_url(),
        },
    )


@router.api_route(
    "/habitaciones/{slug}", methods=["GET", "HEAD"], name="public_room_detail"
)
def public_room_detail(
    request: Request, slug: str, db: Session = Depends(get_public_db)
):
    base_url = get_public_site_base_url()
    room = PublicRoomService().get_room(db, slug, public_base_url=base_url)
    if room is None:
        raise HTTPException(status_code=404)
    canonical = f"{base_url}/habitaciones/{room.slug}" if base_url else None
    og_image = f"{base_url}{room.primary_image.url_1600}" if base_url else None
    return templates.TemplateResponse(
        request=request,
        name="room_detail.html",
        context={
            "request": request,
            "site_name": get_public_site_name(),
            "room": room,
            "canonical": canonical,
            "og_image": og_image,
        },
    )


@router.api_route(
    "/media/{storage_key}/{width}.webp", methods=["GET", "HEAD"], name="public_media"
)
def public_media(
    request: Request,
    storage_key: str,
    width: str,
    db: Session = Depends(get_public_db),
):
    if not width.isdigit():
        raise HTTPException(status_code=404)
    variant = int(width)
    if not STORAGE_KEY_PATTERN.fullmatch(storage_key) or variant not in PUBLIC_IMAGE_WIDTHS:
        raise HTTPException(status_code=404)
    asset = db.query(MediaAsset).filter(
        MediaAsset.storage_key == storage_key,
        MediaAsset.status == "ready",
    ).one_or_none()
    if asset is None:
        raise HTTPException(status_code=404)
    store: MediaFileStore = request.app.state.public_media_store
    try:
        path = store.asset_file(storage_key, variant)
    except ValueError:
        raise HTTPException(status_code=404) from None
    if not path.is_file() or path.is_symlink():
        raise HTTPException(status_code=404)
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
