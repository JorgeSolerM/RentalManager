from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from backend.core.business_time import business_today
from backend.database.session import get_db
from backend.models.booking import Booking
from backend.services.financial_service import FinancialService
from backend.services.manual_payment_service import ManualPaymentService, METHODS, ALL_METHODS
from backend.services.sepa_collection_service import SepaCollectionService
from backend.services.collection_plan_service import CollectionPlanService
from backend.services.financial_account_view import account_view, movement_label


router = APIRouter(prefix="/bookings")
templates = Jinja2Templates(directory="backend/templates")
service = FinancialService()
manual_payments = ManualPaymentService()


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
        charge.type == "security_deposit" and charge.lifecycle != "void"
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
    payments = manual_payments.history(db, booking_id)
    account = account_view(db, charges, balances, payments, business_today())
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
            "payments": payments,
            "account": account,
            "movement_label": movement_label,
            "plan_token": CollectionPlanService().review_token(booking, confirmed_terms) if confirmed_terms and not preview_error else None,
            "payment_methods": ALL_METHODS,
            "sepa_warnings": SepaCollectionService().booking_warnings(db, booking_id),
        },
        headers={"Cache-Control": "private, no-store"},
    )


@router.post('/{booking_id}/finance/plan')
def generate_collection_plan(booking_id: int, terms_id: int = Form(...),
        review_token: str = Form(''), confirm_plan: str = Form(''),
        include_deposit: bool = Form(False), db: Session = Depends(get_db)):
    from urllib.parse import quote
    try:
        if confirm_plan != 'yes':
            raise ValueError('Confirme que ha revisado el plan y su contabilización.')
        CollectionPlanService().generate(db, booking_id, terms_id, review_token=review_token,
                                         include_deposit=include_deposit)
        return _redirect(booking_id, 'success', 'financial_charges_posted')
    except ValueError as error:
        db.rollback()
        # Rendered by the finance page, not an unhandled JSON validation response.
        return RedirectResponse(f'/bookings/{booking_id}/finance?plan_error={quote(str(error))}', status_code=303)
    except SQLAlchemyError:
        db.rollback()
        return RedirectResponse(f'/bookings/{booking_id}/finance?plan_error=No+se+pudo+generar+el+plan.+La+operación+se+ha+revertido.', status_code=303)


def payment_page(request, db, booking_id, *, values=None, rows=None, error=None, status=200):
    return templates.TemplateResponse(request=request, name='pages/booking_payment.html',
        context={'booking':_booking(db,booking_id), 'today':business_today(), 'methods':METHODS,
            'values':values or {}, 'rows':rows, 'error':error, 'request_key':str(uuid4()),
            'warnings':SepaCollectionService().booking_warnings(db,booking_id)},
        status_code=status, headers={'Cache-Control':'private, no-store'})


@router.get('/{booking_id}/finance/payments/new')
def new_payment(request:Request, booking_id:int, db:Session=Depends(get_db)):
    return payment_page(request,db,booking_id)


@router.post('/{booking_id}/finance/payments/{action}')
async def register_manual_payment(request:Request, booking_id:int, action:str, db:Session=Depends(get_db)):
    _booking(db,booking_id)
    form=await request.form()
    values={key:str(form.get(key,'')) for key in ('amount','effective_date','method','reference','notes')}
    try:
        try:
            amount=service._money(values['amount'],allow_zero=False)
            effective=date.fromisoformat(values['effective_date'])
        except (ValueError, TypeError, ArithmeticError):
            raise ValueError('Revise el importe y la fecha del cobro.') from None
        if values['method'] not in METHODS or effective > business_today():
            raise ValueError('Revise el método y la fecha efectiva del cobro.')
        if action=='preview':
            rows, _ = manual_payments.propose(db,booking_id,amount)
            return payment_page(request,db,booking_id,values=values,rows=rows)
        if action!='register': raise ValueError('Acción no válida.')
        pairs=[]
        try:
            for key,value in form.multi_items():
                if key.startswith('allocation_') and value and Decimal(str(value)) != 0:
                    pairs.append((int(key.removeprefix('allocation_')),str(value)))
        except (ValueError, ArithmeticError):
            raise ValueError('Distribución no válida.') from None
        manual_payments.register(db,booking_id,amount=amount,effective_date=effective,
            method=values['method'],allocations=pairs,request_key=str(form.get('request_key','')),
            reference=values['reference'],notes=values['notes'],allow_unallocated=form.get('allow_unallocated')=='yes')
        return RedirectResponse(f'/bookings/{booking_id}/finance',status_code=303)
    except ValueError as error:
        db.rollback()
        return payment_page(request,db,booking_id,values=values,error=str(error),status=400)
    except SQLAlchemyError:
        db.rollback()
        return payment_page(request,db,booking_id,values=values,error='No se pudo registrar el pago. La operación se ha revertido íntegramente.',status=500)


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
