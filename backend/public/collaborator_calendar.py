"""Read-only collaborator projection; no administrative DTOs or booking IDs."""
from datetime import timedelta
from hashlib import sha256
from hmac import compare_digest
import os
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.core.business_time import business_today
from backend.core.public_availability import add_calendar_months, terminal_available_from
from backend.public.database import get_public_db
from backend.public.service import PublicRoomService

PREFIX = '/colaboradores/disponibilidad'
router = APIRouter()
templates = Jinja2Templates(directory='backend/public/templates')


def configured_digest():
    # Absence is the feature flag: fail closed, no migration or secret in Git.
    value = os.getenv('COLLABORATOR_CALENDAR_TOKEN_SHA256', '')
    private_file = os.getenv('COLLABORATOR_CALENDAR_TOKEN_HASH_FILE', '')
    if private_file:
        try:
            value = Path(private_file).read_text(encoding='utf-8').strip()
        except (OSError, UnicodeError):
            raise HTTPException(404, 'No disponible') from None
    if not re.fullmatch(r'[a-f0-9]{64}', value):
        raise HTTPException(404, 'No disponible')
    return value


def authorize(authorization: str | None = Header(default=None)):
    expected = configured_digest()
    token = authorization[7:] if authorization and authorization.startswith('Bearer ') else ''
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token) or not compare_digest(sha256(token.encode()).hexdigest(), expected):
        raise HTTPException(401, 'Enlace no válido o revocado')


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
        group['rooms'].append({
            'name': room.public_title.strip(), 'listing_url': listing_path(room.public_slug),
            'available_from': available.isoformat(),
            'occupied': [{'start': start.isoformat(), 'end': finish.isoformat()} for start, finish in occupied],
        })
    result = sorted(groups.values(), key=lambda group: group['name'].casefold())
    return {'start': today.isoformat(), 'end': end.isoformat(), 'last_day': (end-timedelta(days=1)).isoformat(), 'properties': result}


@router.get(PREFIX, name='collaborator_calendar')
def calendar_page(request: Request):
    configured_digest()
    # This public shell contains no availability. Secret lives in URL fragment,
    # never query/path/server HTML; authenticated data uses an Authorization header.
    return templates.TemplateResponse(request=request, name='collaborator_calendar.html', context={'request': request})


@router.get(PREFIX + '/data', dependencies=[Depends(authorize)])
def calendar_response(request: Request, db: Session = Depends(get_public_db)):
    return calendar_data(db, today=business_today(),
                         listing_path=lambda slug: str(request.app.url_path_for('public_room_detail', slug=slug)))
