from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.services.master_calendar_service import MasterCalendarService
from backend.services.master_calendar_observation_service import (
    MasterCalendarObservationService,
)


router = APIRouter()
service = MasterCalendarService()
observation_service = MasterCalendarObservationService()


def _headers(etag: str) -> dict[str, str]:
    return {
        "Cache-Control": "private, max-age=300, must-revalidate",
        "Content-Disposition": 'inline; filename="calendar.ics"',
        "ETag": etag,
        "X-Content-Type-Options": "nosniff",
    }


@router.get("/ical/rooms/{token}/{platform_slug}.ics")
def get_master_calendar(
    token: str,
    platform_slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    export = service.export_for_platform(db, token, platform_slug)
    if export is None:
        raise HTTPException(status_code=404, detail="Calendario no encontrado.")
    headers = _headers(export.etag)
    observation_service.observe(db, export.room_id, export.platform_id)
    if request.headers.get("if-none-match") == export.etag:
        return Response(status_code=304, headers=headers)
    return Response(
        content=export.content,
        media_type="text/calendar; charset=utf-8",
        headers=headers,
    )


@router.post("/master-calendars/rooms/{room_id}/regenerate")
def regenerate_master_calendar(
    room_id: int,
    db: Session = Depends(get_db),
):
    result = service.regenerate_token(db, room_id)
    if not result.success:
        raise HTTPException(status_code=404, detail="Habitación no encontrada.")
    return RedirectResponse(
        url=f"/rooms/{room_id}?success=master_calendar_token_regenerated",
        status_code=303,
    )
