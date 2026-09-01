from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.core.business_time import business_today
from backend.services.person_service import PersonService


router = APIRouter(prefix="/persons")
templates = Jinja2Templates(directory="backend/templates")
service = PersonService()


@router.get("")
def list_persons(
    request: Request,
    q: str = "",
    sort: str = "name",
    direction: str = "asc",
    db: Session = Depends(get_db),
):
    sort = sort if sort in {"name", "property"} else "name"
    direction = direction if direction in {"asc", "desc"} else "asc"
    today = business_today()
    rows = []
    for person in service.repository.list(db, q):
        current_properties = {
            party.booking.room.property.id: party.booking.room.property
            for party in person.booking_parties
            if party.booking.check_in <= today < party.booking.check_out
        }
        properties = sorted(
            current_properties.values(),
            key=lambda item: (item.name.casefold(), item.id),
        )
        display_name = person.display_name or person.full_name
        name_parts = display_name.split()
        initials = (
            (name_parts[0][0] + name_parts[-1][0]).upper()
            if len(name_parts) > 1
            else name_parts[0][:2].upper()
        )
        rows.append(
            {
                "person": person,
                "current_properties": properties,
                "has_booking_history": bool(person.booking_parties),
                "avatar_initials": initials,
            }
        )

    name_key = lambda row: (
        (row["person"].display_name or row["person"].full_name).casefold(),
        row["person"].full_name.casefold(),
        row["person"].id,
    )
    if sort == "name":
        rows.sort(key=lambda row: row["person"].id)
        rows.sort(
            key=lambda row: name_key(row)[:2],
            reverse=direction == "desc",
        )
    else:
        current = [row for row in rows if row["current_properties"]]
        without_current = [row for row in rows if not row["current_properties"]]
        current.sort(key=name_key)
        current.sort(
            key=lambda row: tuple(
                item.name.casefold() for item in row["current_properties"]
            ),
            reverse=direction == "desc",
        )
        historical = sorted(
            (row for row in without_current if row["has_booking_history"]),
            key=name_key,
        )
        never_linked = sorted(
            (row for row in without_current if not row["has_booking_history"]),
            key=name_key,
        )
        rows = current + historical + never_linked

    def sort_url(column: str) -> str:
        next_direction = (
            "desc" if sort == column and direction == "asc" else "asc"
        )
        return "/persons?" + urlencode(
            {"q": q, "sort": column, "direction": next_direction}
        )

    return templates.TemplateResponse(
        request=request,
        name="pages/persons.html",
        context={
            "request": request,
            "rows": rows,
            "query": q,
            "sort": sort,
            "direction": direction,
            "name_sort_url": sort_url("name"),
            "property_sort_url": sort_url("property"),
        },
    )


@router.get("/options")
def person_options(q: str = "", db: Session = Depends(get_db)):
    return [{"id": person.id, "name": person.display_name or person.full_name} for person in service.repository.list(db, q) if person.active]


@router.get("/new")
def new_person(request: Request):
    return templates.TemplateResponse(request=request, name="pages/person_form.html", context={"request": request, "person": None})


@router.get("/{person_id}")
def person_detail(request: Request, person_id: int, db: Session = Depends(get_db)):
    person = service.repository.get(db, person_id)
    if person is None: raise HTTPException(404, "Persona no encontrada")
    return templates.TemplateResponse(
        request=request,
        name="pages/person_detail.html",
        context={"request": request, "person": person, "today": business_today()},
    )


@router.get("/{person_id}/edit")
def edit_person(request: Request, person_id: int, db: Session = Depends(get_db)):
    person = service.repository.get(db, person_id)
    if person is None: raise HTTPException(404, "Persona no encontrada")
    return templates.TemplateResponse(request=request, name="pages/person_form.html", context={"request": request, "person": person})


def _save(db, person_id, full_name, display_name, phone, email, iban, document_type, document_number, document_issuer_country, birth_date, nationality, address_line, postal_code, city, province, country, notes, verification_status, active):
    return service.save(db, person_id, full_name=full_name, display_name=display_name, phone=phone, email=email, iban=iban, document_type=document_type, document_number=document_number, document_issuer_country=document_issuer_country, birth_date=birth_date, nationality=nationality, address_line=address_line, postal_code=postal_code, city=city, province=province, country=country, notes=notes, verification_status=verification_status, active=active)


@router.post("/create")
def create_person(full_name: str = Form(...), display_name: str = Form(""), phone: str = Form(""), email: str = Form(""), iban: str = Form(""), document_type: str = Form(""), document_number: str = Form(""), document_issuer_country: str = Form(""), birth_date: date | None = Form(None), nationality: str = Form(""), address_line: str = Form(""), postal_code: str = Form(""), city: str = Form(""), province: str = Form(""), country: str = Form(""), notes: str = Form(""), verification_status: str = Form("unverified"), active: bool = Form(False), db: Session = Depends(get_db)):
    result = _save(db, None, full_name, display_name, phone, email, iban, document_type, document_number, document_issuer_country, birth_date, nationality, address_line, postal_code, city, province, country, notes, verification_status, active)
    return RedirectResponse(f"/persons/{result.data.id}" if result.success else f"/persons/new?error={result.message}", 303)


@router.post("/{person_id}/update")
def update_person(person_id: int, full_name: str = Form(...), display_name: str = Form(""), phone: str = Form(""), email: str = Form(""), iban: str = Form(""), document_type: str = Form(""), document_number: str = Form(""), document_issuer_country: str = Form(""), birth_date: date | None = Form(None), nationality: str = Form(""), address_line: str = Form(""), postal_code: str = Form(""), city: str = Form(""), province: str = Form(""), country: str = Form(""), notes: str = Form(""), verification_status: str = Form("unverified"), active: bool = Form(False), db: Session = Depends(get_db)):
    result = _save(db, person_id, full_name, display_name, phone, email, iban, document_type, document_number, document_issuer_country, birth_date, nationality, address_line, postal_code, city, province, country, notes, verification_status, active)
    return RedirectResponse(f"/persons/{person_id}?{'success=person_saved' if result.success else 'error='+result.message}", 303)


@router.post("/{person_id}/delete")
def delete_person(person_id: int, db: Session = Depends(get_db)):
    result = service.delete(db, person_id)
    return RedirectResponse("/persons?success=person_deleted" if result.success else f"/persons/{person_id}?error={result.message}", 303)
