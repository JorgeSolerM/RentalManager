from datetime import date
import re
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.core.business_time import business_today
from backend.core.config import (
    get_public_contact_config,
    get_public_legal_config,
    get_public_site_base_url,
    get_public_site_name,
)
from backend.core.media_storage import PUBLIC_IMAGE_WIDTHS, MediaFileStore
from backend.core.public_phone import phone_link_values, whatsapp_url
from backend.models.media_asset import MediaAsset
from backend.public.database import get_public_db
from backend.public.service import PublicRoomService


router = APIRouter()
templates = Jinja2Templates(directory="backend/public/templates")
STORAGE_KEY_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def _public_base_url(request: Request) -> str:
    return (get_public_site_base_url() or str(request.base_url)).rstrip("/")


@router.api_route("/", methods=["GET", "HEAD"], name="public_catalog")
def public_catalog(request: Request, db: Session = Depends(get_public_db)):
    today = business_today()
    raw_check_in = request.query_params.get("check_in", "").strip()
    raw_check_out = request.query_params.get("check_out", "").strip()
    selected_sort = PublicRoomService.normalize_sort(
        request.query_params.get("sort", "recommended").strip()
    )

    raw_feature_values = request.query_params.getlist("features")
    selected_features = tuple(dict.fromkeys(
        slug.strip()
        for value in raw_feature_values
        for slug in value.split(",")
        if slug.strip()
    ))
    errors = []
    requested_check_in = requested_check_out = None
    if bool(raw_check_in) != bool(raw_check_out):
        errors.append("Indica tanto la fecha de entrada como la de salida.")
    elif raw_check_in and raw_check_out:
        try:
            requested_check_in = date.fromisoformat(raw_check_in)
            requested_check_out = date.fromisoformat(raw_check_out)
        except ValueError:
            errors.append("Las fechas indicadas no son válidas.")
        else:
            if requested_check_in < today:
                errors.append("La fecha de entrada no puede estar en el pasado.")
            elif requested_check_out <= requested_check_in:
                errors.append("La fecha de salida debe ser posterior a la entrada.")

    service = PublicRoomService()
    available_features = service.list_filter_features(db)
    allowed_slugs = {feature.slug for feature in available_features}
    selected_features = tuple(slug for slug in selected_features if slug in allowed_slugs)
    has_valid_dates = requested_check_in is not None and not errors
    base_url = _public_base_url(request)
    rooms = service.list_rooms(
        db,
        today=today,
        requested_check_in=requested_check_in if has_valid_dates else None,
        requested_check_out=requested_check_out if has_valid_dates else None,
        feature_slugs=selected_features,
        public_base_url=base_url,
        sort=selected_sort,
    )
    hero_image = rooms[0].primary_image if rooms else None
    contact_room_url = rooms[0].contact_url if rooms else None
    page_url = f"{base_url}/"
    og_image = f"{base_url}{hero_image.url_1600}" if hero_image else None
    return templates.TemplateResponse(
        request=request,
        name="catalog.html",
        context={
            "request": request,
            "site_name": get_public_site_name(),
            "rooms": rooms,
            "base_url": base_url,
            "filter_features": available_features,
            "selected_features": set(selected_features),
            "check_in": raw_check_in,
            "check_out": raw_check_out,
            "filter_errors": errors,
            "filters_active": bool(raw_check_in or raw_check_out or selected_features),
            "date_filter_active": has_valid_dates,
            "selected_sort": selected_sort,
            "hero_image": hero_image,
            "header_contact_url": contact_room_url,
            "page_url": page_url,
            "og_image": og_image,
        },
    )


@router.api_route("/contacto", methods=["GET", "HEAD"], name="public_contact")
def public_contact(request: Request):
    base_url = _public_base_url(request)
    contact = get_public_contact_config()
    phone_values = phone_link_values(contact.phone)
    contact_whatsapp_url = whatsapp_url(
        contact.whatsapp_number,
        "Hola, me gustaría recibir información sobre las habitaciones de HSI Rents.",
    )
    canonical = f"{base_url}/contacto"
    return templates.TemplateResponse(
        request=request,
        name="contact.html",
        context={
            "request": request,
            "site_name": get_public_site_name(),
            "contact": contact,
            "tel_url": phone_values[1] if phone_values else None,
            "whatsapp_url": contact_whatsapp_url,
            "header_contact_url": contact_whatsapp_url,
            "canonical": canonical,
        },
    )


def _render_legal_page(
    request: Request, *, template_name: str, template_title: str, page_path: str
):
    canonical = f"{_public_base_url(request)}/{page_path}"
    return templates.TemplateResponse(
        request=request,
        name=template_name,
        context={
            "request": request,
            "site_name": get_public_site_name(),
            "template_title": template_title,
            "canonical": canonical,
            "contact": get_public_contact_config(),
            "legal": get_public_legal_config(),
        },
    )


@router.api_route(
    "/aviso-legal", methods=["GET", "HEAD"], name="public_legal_notice"
)
def public_legal_notice(request: Request):
    return _render_legal_page(
        request,
        template_name="legal_notice.html",
        template_title="Aviso legal",
        page_path="aviso-legal",
    )


@router.api_route(
    "/privacidad", methods=["GET", "HEAD"], name="public_privacy"
)
def public_privacy(request: Request):
    return _render_legal_page(
        request,
        template_name="privacy.html",
        template_title="Política de privacidad",
        page_path="privacidad",
    )


@router.api_route("/cookies", methods=["GET", "HEAD"], name="public_cookies")
def public_cookies(request: Request):
    return _render_legal_page(
        request,
        template_name="cookies.html",
        template_title="Política de cookies",
        page_path="cookies",
    )


@router.api_route("/robots.txt", methods=["GET", "HEAD"], name="public_robots")
def public_robots(request: Request):
    base_url = _public_base_url(request)
    return PlainTextResponse(
        f"User-agent: *\nAllow: /\nSitemap: {base_url}/sitemap.xml\n",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.api_route("/sitemap.xml", methods=["GET", "HEAD"], name="public_sitemap")
def public_sitemap(request: Request, db: Session = Depends(get_public_db)):
    base_url = _public_base_url(request)
    rooms = PublicRoomService().list_rooms(db, public_base_url=base_url)
    locations = [f"{base_url}/", f"{base_url}/contacto", *(
        f"{base_url}/habitaciones/{room.slug}" for room in rooms
    )]
    entries = "".join(f"<url><loc>{escape(url)}</loc></url>" for url in locations)
    document = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{entries}</urlset>"
    )
    return Response(
        document,
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.api_route(
    "/habitaciones/{slug}", methods=["GET", "HEAD"], name="public_room_detail"
)
def public_room_detail(
    request: Request, slug: str, db: Session = Depends(get_public_db)
):
    base_url = _public_base_url(request)
    room = PublicRoomService().get_room(db, slug, public_base_url=base_url)
    if room is None:
        raise HTTPException(status_code=404)
    canonical = f"{base_url}/habitaciones/{room.slug}"
    og_image = f"{base_url}{room.primary_image.url_1600}"
    return templates.TemplateResponse(
        request=request,
        name="room_detail.html",
        context={
            "request": request,
            "site_name": get_public_site_name(),
            "room": room,
            "canonical": canonical,
            "og_image": og_image,
            "header_contact_url": room.manager.whatsapp_url,
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
