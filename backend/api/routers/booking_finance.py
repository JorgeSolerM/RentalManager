from datetime import timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.core.business_time import business_today
from backend.database.session import get_db
from backend.models.booking import Booking
from backend.services.financial_service import FinancialService


router = APIRouter(prefix="/bookings")
templates = Jinja2Templates(directory="backend/templates")
service = FinancialService()


def _inclusive_period_end(period_end):
    """Format helper only; stored service periods remain half-open [start, end)."""
    return period_end - timedelta(days=1)


def _booking(db: Session, booking_id: int) -> Booking:
    booking = db.get(Booking, booking_id)
    if booking is None:
        raise HTTPException(404, "Reserva no encontrada.")
    return booking


def _redirect(booking_id: int, kind: str, message: str):
    return RedirectResponse(
        f"/bookings/{booking_id}/finance?{kind}={message}", status_code=303
    )


@router.get("/{booking_id}/finance")
def booking_finance(
    request: Request,
    booking_id: int,
    use_legacy_price: bool = False,
    db: Session = Depends(get_db),
):
    booking = _booking(db, booking_id)
    terms_versions = service.repository.list_terms(db, booking_id)
    latest_terms = terms_versions[-1] if terms_versions else None
    confirmed_terms = next(
        (item for item in reversed(terms_versions) if item.status == "confirmed"),
        None,
    )
    charges = service.repository.list_charges(db, booking_id)
    deposit_generated = any(
        charge.type == "security_deposit" and charge.lifecycle == "draft"
        for charge in charges
    )
    balances = {charge.id: service.charge_balance(db, charge.id) for charge in charges}
    summary = service.booking_summary(db, booking_id)
    generation_state = service.generation_state(db, booking, confirmed_terms)
    preview = []
    preview_error = None
    if confirmed_terms is not None:
        try:
            preview = service.preview_for_booking(booking, confirmed_terms)
        except ValueError as error:
            preview_error = str(error)
    tenants = [
        party for party in booking.parties if party.role == "tenant"
    ]
    payers = [
        party for party in booking.parties if party.role == "payer"
    ]
    legacy = service.legacy_price_candidate(db, booking_id)
    suggested_rent = (
        legacy.amount if use_legacy_price and legacy is not None else None
    )
    total_expected = sum((row.amount for row in preview), Decimal("0.00"))
    if confirmed_terms is not None:
        total_expected += confirmed_terms.deposit_agreed
    return templates.TemplateResponse(
        request=request,
        name="pages/booking_finance.html",
        context={
            "request": request,
            "booking": booking,
            "terms_versions": terms_versions,
            "latest_terms": latest_terms,
            "confirmed_terms": confirmed_terms,
            "charges": charges,
            "deposit_generated": deposit_generated,
            "balances": balances,
            "summary": summary,
            "generation_state": generation_state,
            "preview": preview,
            "preview_error": preview_error,
            "tenants": tenants,
            "payers": payers,
            "legacy": legacy,
            "suggested_rent": suggested_rent,
            "total_expected": total_expected,
            "today": business_today(),
            "inclusive_period_end": _inclusive_period_end,
        },
    )


@router.post("/{booking_id}/finance/terms")
def save_financial_terms(
    booking_id: int,
    monthly_rent: Decimal = Form(...),
    deposit_agreed: Decimal = Form(Decimal("0.00")),
    usual_due_day: int = Form(1),
    db: Session = Depends(get_db),
):
    booking = _booking(db, booking_id)
    latest = service.repository.latest_terms(db, booking_id)
    if latest is not None and latest.status == "draft":
        result = service.update_terms_draft(
            db,
            latest.id,
            effective_from=booking.check_in,
            effective_until=None,
            monthly_rent=monthly_rent,
            deposit_agreed=deposit_agreed,
            usual_due_day=usual_due_day,
            currency="EUR",
        )
    elif latest is None:
        result = service.create_terms_draft(
            db,
            booking_id,
            booking.check_in,
            monthly_rent,
            deposit_agreed=deposit_agreed,
            usual_due_day=usual_due_day,
        )
    else:
        return _redirect(booking_id, "error", "financial_terms_immutable")
    return _redirect(
        booking_id,
        "success" if result.success else "error",
        "financial_terms_saved" if result.success else result.message,
    )


@router.post("/{booking_id}/finance/terms/{terms_id}/confirm")
def confirm_financial_terms(
    booking_id: int, terms_id: int, db: Session = Depends(get_db)
):
    terms = service.repository.get_terms(db, terms_id)
    if terms is None or terms.booking_id != booking_id:
        raise HTTPException(404, "Condiciones económicas no encontradas.")
    result = service.confirm_terms(db, terms_id)
    return _redirect(
        booking_id,
        "success" if result.success else "error",
        "financial_terms_confirmed" if result.success else result.message,
    )


@router.post("/{booking_id}/finance/generate")
def generate_financial_charges(
    booking_id: int,
    terms_id: int = Form(...),
    include_deposit: bool = Form(False),
    db: Session = Depends(get_db),
):
    result = service.generate_booking_charges(
        db, booking_id, terms_id, include_deposit=include_deposit
    )
    return _redirect(
        booking_id,
        "success" if result.success else "error",
        "financial_charges_generated" if result.success else result.message,
    )


@router.post("/{booking_id}/finance/regenerate")
def regenerate_financial_charges(
    booking_id: int,
    terms_id: int = Form(...),
    include_deposit: bool = Form(False),
    db: Session = Depends(get_db),
):
    result = service.regenerate_draft_charges(
        db, booking_id, terms_id, include_deposit=include_deposit
    )
    return _redirect(
        booking_id,
        "success" if result.success else "error",
        "financial_charges_regenerated" if result.success else result.message,
    )


@router.post("/{booking_id}/finance/post")
def post_financial_charges(booking_id: int, db: Session = Depends(get_db)):
    _booking(db, booking_id)
    result = service.post_generated_drafts(db, booking_id)
    return _redirect(
        booking_id,
        "success" if result.success else "error",
        "financial_charges_posted" if result.success else result.message,
    )
