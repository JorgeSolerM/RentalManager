from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.services.room_calendar_service import RoomCalendarService
from backend.services.ical_sync_service import IcalSyncService


router = APIRouter(prefix="/room-calendars")
service = RoomCalendarService()
ical_sync_service = IcalSyncService()


def _redirect(room_id: int, kind: str, message: str) -> RedirectResponse:
    return RedirectResponse(
        url=f"/rooms/{room_id}?{kind}={message}",
        status_code=303,
    )


@router.post("/create")
def create_calendar(
    room_id: int = Form(...),
    platform_id: int = Form(...),
    import_url: str = Form(""),
    db: Session = Depends(get_db),
):
    result = service.create_calendar(db, room_id, platform_id, import_url)
    if result.success:
        return _redirect(room_id, "success", "room_calendar_created")
    return _redirect(room_id, "error", result.message)


@router.post("/update/{calendar_id}")
def update_calendar(
    calendar_id: int,
    import_url: str = Form(""),
    db: Session = Depends(get_db),
):
    result = service.update_calendar(db, calendar_id, import_url)
    if not result.success and result.message == "not_found":
        raise HTTPException(status_code=404, detail="Calendario no encontrado.")
    if result.success:
        return _redirect(result.data.room_id, "success", "room_calendar_updated")
    return _redirect(result.data.room_id, "error", result.message)


@router.post("/toggle/{calendar_id}")
def toggle_calendar(calendar_id: int, db: Session = Depends(get_db)):
    result = service.toggle_calendar(db, calendar_id)
    if not result.success and result.message == "not_found":
        raise HTTPException(status_code=404, detail="Calendario no encontrado.")
    if result.success:
        return _redirect(result.data.room_id, "success", "room_calendar_toggled")
    return _redirect(result.data.room_id, "error", result.message)


@router.post("/delete/{calendar_id}")
def delete_calendar(calendar_id: int, db: Session = Depends(get_db)):
    result = service.delete_calendar(db, calendar_id)
    if not result.success and result.message == "not_found":
        raise HTTPException(status_code=404, detail="Calendario no encontrado.")
    if result.success:
        return _redirect(result.data.room_id, "success", "room_calendar_deleted")
    return _redirect(result.data.room_id, "error", result.message)


@router.post("/{calendar_id}/sync")
def sync_calendar(calendar_id: int, db: Session = Depends(get_db)):
    calendar = service.get_by_id(db, calendar_id)
    if calendar is None:
        raise HTTPException(status_code=404, detail="Calendario no encontrado.")
    room_id = calendar.room_id
    result = ical_sync_service.synchronize(db, calendar_id)
    kind = "success" if result.success else "error"
    return _redirect(room_id, kind, result.message)
