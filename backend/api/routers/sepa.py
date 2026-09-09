from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.services.booking_service import BookingService
from backend.services.owner_service import OwnerService
from backend.services.sepa_service import SepaService


router = APIRouter(prefix="/sepa")
templates = Jinja2Templates(directory="backend/templates")
service = SepaService()
owner_service = OwnerService()
booking_service = BookingService()


@router.post("/references")
def generate_reference(creditor_profile_id: int = Form(...), db: Session = Depends(get_db)):
    result = service.generate_reference(db, creditor_profile_id)
    if not result.success:
        raise HTTPException(409, "Selecciona un acreedor activo con numeración disponible.")
    return {"reference": result.data}


@router.post("/owners/{owner_id}/profiles")
@router.post("/owners/{owner_id}/profiles/{profile_id}")
def save_profile(owner_id: int, profile_id: int | None = None,
                 display_name: str = Form(...), creditor_name: str = Form(...),
                 creditor_identifier: str = Form(...), bank_account_id: int = Form(...),
                 scheme: str = Form("CORE"), active: bool = Form(False), notes: str = Form(""),
                 db: Session = Depends(get_db)):
    if owner_service.repository.get(db, owner_id) is None:
        raise HTTPException(404, "Propietario no encontrado")
    result = service.save_profile(db, profile_id, display_name=display_name,
                                  creditor_name=creditor_name, creditor_identifier=creditor_identifier,
                                  owner_id=owner_id, bank_account_id=bank_account_id, scheme=scheme,
                                  active=active, notes=notes)
    return RedirectResponse(f"/owners/{owner_id}?{'success=sepa_profile_saved' if result.success else 'error='+result.message}", 303)


def _save_mandate(db, mandate_id, creditor_profile_id, person_id, debtor_name,
                  debtor_iban, debtor_bic, mandate_reference, signature_date,
                  mandate_type, status, amendment_indicator, active_from,
                  cancelled_at, notes):
    return service.save_mandate(
        db, mandate_id, creditor_profile_id=creditor_profile_id, person_id=person_id,
        debtor_name=debtor_name, debtor_iban=debtor_iban, debtor_bic=debtor_bic,
        mandate_reference=mandate_reference, signature_date=signature_date,
        mandate_type=mandate_type, status=status, amendment_indicator=amendment_indicator,
        active_from=active_from, cancelled_at=cancelled_at, notes=notes,
    )


@router.post("/persons/{person_id}/mandates")
@router.post("/persons/{person_id}/mandates/{mandate_id}")
def save_person_mandate(person_id: int, mandate_id: int | None = None,
                        creditor_profile_id: int = Form(...), debtor_name: str = Form(...),
                        debtor_iban: str = Form(...), debtor_bic: str = Form(""),
                        mandate_reference: str = Form(...), signature_date: date = Form(...),
                        mandate_type: str = Form("RCUR"), status: str = Form("draft"),
                        amendment_indicator: bool = Form(False), active_from: date | None = Form(None),
                        cancelled_at: date | None = Form(None), notes: str = Form(""),
                        db: Session = Depends(get_db)):
    result = _save_mandate(db, mandate_id, creditor_profile_id, person_id, debtor_name,
                           debtor_iban, debtor_bic, mandate_reference, signature_date,
                           mandate_type, status, amendment_indicator, active_from,
                           cancelled_at, notes)
    return RedirectResponse(f"/persons/{person_id}?{'success=sepa_mandate_saved' if result.success else 'error='+result.message}", 303)


@router.get("/bookings/{booking_id}")
def booking_sepa(request: Request, booking_id: int, db: Session = Depends(get_db)):
    booking = service.repository.get_booking(db, booking_id)
    if booking is None:
        raise HTTPException(404, "Reserva no encontrada")
    profiles = service.repository.compatible_profiles(db, booking)
    mandates = service.repository.compatible_mandates(db, booking)
    payers = [item.person for item in booking.parties if item.role == "payer"]
    return templates.TemplateResponse(
        request=request, name="pages/booking_sepa.html",
        context={"request": request, "booking": booking, "profiles": profiles,
                 "mandates": mandates, "payers": payers,
                 "active_link": booking.active_sepa_mandate_link},
    )


@router.post("/bookings/{booking_id}/link")
def link_booking_mandate(booking_id: int, mandate_id: int = Form(...), db: Session = Depends(get_db)):
    result = service.link_booking(db, booking_id, mandate_id)
    return RedirectResponse(f"/sepa/bookings/{booking_id}?{'success=sepa_mandate_linked' if result.success else 'error='+result.message}", 303)


@router.post("/bookings/{booking_id}/unlink")
def unlink_booking_mandate(booking_id: int, db: Session = Depends(get_db)):
    result = service.unlink_booking(db, booking_id)
    return RedirectResponse(f"/sepa/bookings/{booking_id}?{'success=sepa_mandate_unlinked' if result.success else 'error='+result.message}", 303)


@router.post("/bookings/{booking_id}/mandates")
def create_booking_mandate(booking_id: int, creditor_profile_id: int = Form(...),
                           person_id: int | None = Form(None), debtor_name: str = Form(...),
                           debtor_iban: str = Form(...), debtor_bic: str = Form(""),
                           mandate_reference: str = Form(...), signature_date: date = Form(...),
                           mandate_type: str = Form("RCUR"), status: str = Form("draft"),
                           amendment_indicator: bool = Form(False), active_from: date | None = Form(None),
                           cancelled_at: date | None = Form(None), notes: str = Form(""),
                           link_now: bool = Form(False), db: Session = Depends(get_db)):
    booking = service.repository.get_booking(db, booking_id)
    if booking is None:
        raise HTTPException(404, "Reserva no encontrada")
    if creditor_profile_id not in {p.id for p in service.repository.compatible_profiles(db, booking)}:
        return RedirectResponse(f"/sepa/bookings/{booking_id}?error=sepa_mandate_property_incompatible", 303)
    result = _save_mandate(db, None, creditor_profile_id, person_id, debtor_name,
                           debtor_iban, debtor_bic, mandate_reference, signature_date,
                           mandate_type, status, amendment_indicator, active_from,
                           cancelled_at, notes)
    if not result.success:
        return RedirectResponse(f"/sepa/bookings/{booking_id}?error={result.message}", 303)
    if link_now:
        linked = service.link_booking(db, booking_id, result.data.id)
        if not linked.success:
            return RedirectResponse(f"/sepa/bookings/{booking_id}?error={linked.message}", 303)
    return RedirectResponse(f"/sepa/bookings/{booking_id}?success=sepa_mandate_saved", 303)
