from datetime import date
from uuid import uuid4
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from backend.database.session import get_db
from backend.models.booking import Booking
from backend.services.booking_early_termination_service import BookingEarlyTerminationService

router = APIRouter()
templates = Jinja2Templates(directory='backend/templates')
service = BookingEarlyTerminationService()


def page(request, db, booking_id, *, view=None, error=None, form=None, key=None, status=200):
    booking = db.get(Booking, booking_id)
    if not booking:
        raise HTTPException(404, 'Reserva no encontrada.')
    return templates.TemplateResponse(request=request, name='pages/booking_early_termination.html', context=dict(
        request=request, booking=booking, view=view, error=error, form=form or {}, key=key or str(uuid4())), status_code=status)


@router.get('/{booking_id}/early-termination')
def edit(booking_id:int, request:Request, db=Depends(get_db)):
    return page(request, db, booking_id)


def values(form):
    try:
        return dict(effective_departure=date.fromisoformat(form.get('effective_departure', '')),
            economic_last_day=date.fromisoformat(form.get('economic_last_day', '')), reason=form.get('reason',''),
            notes=form.get('notes',''), accept_proration=form.get('accept_proration') == 'yes')
    except (ValueError, TypeError):
        raise ValueError('Indique fechas válidas de salida y último día a cargo.') from None


@router.post('/{booking_id}/early-termination/preview')
async def preview(booking_id:int, request:Request, db=Depends(get_db)):
    form = await request.form()
    try:
        view = service.preview(db, booking_id, **values(form))
        return page(request, db, booking_id, view=view, form=form, key=form.get('request_key'))
    except ValueError as exc:
        return page(request, db, booking_id, error=str(exc), form=form, status=422)


@router.post('/{booking_id}/early-termination/confirm')
async def confirm(booking_id:int, request:Request, db=Depends(get_db)):
    form = await request.form()
    try:
        if form.get('confirmed') != 'yes':
            raise ValueError('Confirme explícitamente la finalización revisada.')
        service.confirm(db, booking_id, **values(form), expected=form.get('fingerprint',''), request_key=form.get('request_key',''))
        return RedirectResponse(f'/bookings/{booking_id}/early-termination', 303)
    except ValueError as exc:
        return page(request, db, booking_id, error=str(exc), form=form, status=409)
