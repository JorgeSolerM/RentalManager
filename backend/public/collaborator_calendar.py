"""Read-only collaborator projection; no administrative DTOs or booking IDs."""
from datetime import timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.core.business_time import business_today
from backend.core.public_availability import add_calendar_months, terminal_available_from
from backend.public.database import get_public_db
from backend.public.service import PublicRoomService

PREFIX = '/colaboradores/disponibilidad'
router = APIRouter()
templates = Jinja2Templates(directory='backend/public/templates')


def calendar_data(db, *, today, listing_path):
    end = add_calendar_months(today, 6)
    service = PublicRoomService()
    groups = {}
    # Existing public loader selects Booking.check_out > today with NO upper
    # bound, including future reservations beyond the six-month visible window.
    for room in service.repository.list_candidates(db, today):
        if not service._is_publicable(room):
            continue
        intervals = [(b.check_in, b.check_out) for b in room.bookings]
        available = terminal_available_from(intervals, today)
        if available is None or available >= end:
            continue
        occupied = []
        for start, finish in sorted(intervals):
            start, finish = max(today, start), min(end, finish)
            if start >= finish:
                continue
            if occupied and start <= occupied[-1][1]:
                occupied[-1] = (occupied[-1][0], max(finish, occupied[-1][1]))
            else:
                occupied.append((start, finish))
        group = groups.setdefault(room.property_id, {'name': room.property.public_title.strip(), 'rooms': []})
        primary = service._primary_photo(room)
        group['rooms'].append({
            'name': room.public_title.strip(), 'listing_url': listing_path(room.public_slug),
            'slug': room.public_slug,
            'price_monthly': str(room.base_price) if room.base_price is not None else None,
            'thumbnail_url': service._image(primary, service._photo_source(room, primary)).url_320 if primary else None,
            'available_from': available.isoformat(),
            'occupied': [{'start': start.isoformat(), 'end': finish.isoformat()} for start, finish in occupied],
        })
    result = sorted(groups.values(), key=lambda group: group['name'].casefold())
    return {'start': today.isoformat(), 'end': end.isoformat(), 'last_day': (end-timedelta(days=1)).isoformat(), 'properties': result}


@router.get(PREFIX, name='collaborator_calendar')
def calendar_page(request: Request):
    # Explicitly public, read-only projection; no administrative routes.
    return templates.TemplateResponse(request=request, name='collaborator_calendar.html', context={'request': request})


@router.get(PREFIX + '/data')
def calendar_response(request: Request, db: Session = Depends(get_public_db)):
    return calendar_data(db, today=business_today(),
                         listing_path=lambda slug: str(request.app.url_path_for('public_room_detail', slug=slug)))
