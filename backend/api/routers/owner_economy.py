"""Private administrative expenses and owner settlements."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from backend.database.session import get_db
from backend.models.owner import Owner
from backend.models.provider import Provider
from backend.models.property import Property
from backend.models.payment import Payment
from backend.models.owner_bank_account import OwnerBankAccount
from backend.models.owner_settlement import Expense, ExpenseCategory, ManagementFeeTerms, OwnerSettlement, OwnerPayout
from backend.services.expense_service import ExpenseService
from backend.services.owner_settlement_service import OwnerSettlementService
from backend.services.settlement_selection_service import SettlementSelectionService
from backend.core.business_time import business_today

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")
expenses, settlements = ExpenseService(), OwnerSettlementService()
property_selection = SettlementSelectionService()


def page(request, db, mode, **context):
    if mode == 'expense_new':
        context['providers'] = list(db.scalars(select(Provider).where(Provider.active == True).order_by(Provider.legal_name)))
    if mode == 'expense':
        item = context['item']
        context['ownership_info'] = expense_ownership_info(db, item.property_id, item.expense_date)
        context['category'] = db.get(ExpenseCategory, item.category_id)
    return templates.TemplateResponse(request=request, name="pages/owner_economy.html", context={
        "request": request, "mode": mode, "today": business_today(), "key": str(uuid4()),
        "owners": list(db.scalars(select(Owner).order_by(Owner.legal_name))),
        "properties": list(db.scalars(select(Property).order_by(Property.name))), **context})


@router.get("/expenses")
def expense_list(request: Request, db=Depends(get_db)):
    rows = [(e, expenses.balance(db, e.id)) for e in expenses.list(db)]
    return page(request, db, "expenses", rows=rows)


@router.get("/expenses/new")
def expense_new(request: Request, db=Depends(get_db)):
    return page(request, db, "expense_new", values={'provider_id':request.query_params.get('provider_id','')}, categories=list(db.scalars(select(ExpenseCategory).where(ExpenseCategory.active == True))))


def expense_ownership_info(db, property_id, economic_date):
    if db.get(Property, property_id) is None:
        return {'owners': [], 'warning': 'Finca no encontrada.'}
    try:
        relations = settlements.ownership(db, property_id, economic_date)
        owners = {o.id: o.name for o in db.scalars(select(Owner).where(Owner.id.in_([r.owner_id for r in relations])))}
        return {'owners': [{'id': r.owner_id, 'name': owners[r.owner_id], 'percentage': str(r.ownership_percentage)} for r in relations], 'warning': None}
    except ValueError as exc:
        return {'owners': [], 'warning': 'Requiere revisión de titularidad. ' + str(exc)}


@router.get('/expenses/ownership')
def expense_ownership(property_id: int, expense_date: date, db=Depends(get_db)):
    return expense_ownership_info(db, property_id, expense_date)


@router.post("/expenses/new")
async def expense_create(request: Request, db=Depends(get_db)):
    f = await request.form()
    try:
        imputation = f.get('imputation', 'property')
        if imputation not in {'property', 'owner'}:
            raise ValueError('Revise la imputación del gasto.')
        owner_id = None
        if imputation == 'owner':
            if not f.get('owner_id'):
                raise ValueError('Seleccione el propietario específico.')
            owner_id = int(f['owner_id'])
        item = expenses.create(db, property_id=int(f["property_id"]), category_id=int(f["category_id"]),
            expense_date=date.fromisoformat(f["expense_date"]), concept=f["concept"], base_amount=f["base_amount"],
            vat_rate=f["vat_rate"], withholding_rate=f["withholding_rate"],
            owner_id=owner_id, borne_by=f.get('borne_by','owner'), notes=f.get("notes"),
            provider_id=int(f['provider_id']) if f.get('provider_id') else None)
        return RedirectResponse(f"/expenses/{item.id}", 303)
    except (ValueError, KeyError) as exc:
        return page(request, db, "expense_new", error=str(exc), values=dict(f), categories=list(db.scalars(select(ExpenseCategory))))


@router.get("/expenses/{expense_id}")
def expense_detail(request: Request, expense_id: int, db=Depends(get_db)):
    item = db.get(Expense, expense_id)
    if item is None:
        raise HTTPException(404)
    return page(request, db, "expense", item=item, balance=expenses.balance(db, item.id), payments=expenses.payments(db, item.id))


@router.post("/expenses/{expense_id}/payments")
async def expense_pay(request: Request, expense_id: int, db=Depends(get_db)):
    f = await request.form()
    try:
        expenses.pay(db, expense_id, effective_date=date.fromisoformat(f["effective_date"]), amount=f["amount"],
            paid_by=f["paid_by"], paid_by_owner_id=int(f["paid_by_owner_id"]) if f.get("paid_by_owner_id") else None,
            method=f["method"], request_key=f["request_key"], reference=f.get("reference"),
            corrects_id=int(f["corrects_id"]) if f.get("corrects_id") else None)
        return RedirectResponse(f"/expenses/{expense_id}", 303)
    except (ValueError, KeyError) as exc:
        return page(request, db, "expense", item=db.get(Expense, expense_id), error=str(exc),
                    balance=expenses.balance(db, expense_id), payments=expenses.payments(db, expense_id))


@router.get("/settlements")
def settlement_list(request: Request, db=Depends(get_db)):
    return page(request, db, "settlements", items=list(db.scalars(select(OwnerSettlement).order_by(OwnerSettlement.id.desc()))))


@router.get("/settlements/new")
def settlement_new(request: Request, db=Depends(get_db)):
    return selection_page(request, db, request.query_params)


def selection_period(values):
    default = (business_today().replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
    month = values.get('month') or default
    start = date.fromisoformat(month + '-01')
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return month, start, end


def selection_page(request, db, values, error=None):
    try:
        month, start, end = selection_period(values)
    except ValueError:
        month, start, end = selection_period({})
        error = error or 'Mes no válido.'
    return page(request, db, 'settlement_new', month=month, error=error,
                choices=property_selection.catalog(db, start, end))


async def selection(request, db):
    f = await request.form()
    owner_id, start, end = int(f["owner_id"]), date.fromisoformat(f["start"]), date.fromisoformat(f["end"])
    properties = [int(v) for v in f.getlist("property_id")]
    excluded = []
    if f.get("selection_present"):
        all_keys = settlements.preview(db, owner_id, start, end, properties)["rows"]
        included = set(f.getlist("include"))
        excluded = [r["key"] for r in all_keys if r["kind"] != "prior_balance" and r["key"] not in included]
    return f, owner_id, start, end, properties, excluded


@router.post("/settlements/preview")
async def settlement_preview(request: Request, db=Depends(get_db)):
    f = await request.form()
    try:
        month, start, end = selection_period(f)
        result = property_selection.preview(db, start, end, f.getlist('property_id'))
        return page(request, db, 'selection_preview', batch=result, month=month)
    except (ValueError, KeyError) as exc:
        return selection_page(request, db, f, str(exc))


@router.post('/settlements/drafts')
async def settlement_drafts(request: Request, db=Depends(get_db)):
    f = await request.form()
    try:
        _, start, end = selection_period(f)
        items = property_selection.save_drafts(db, start, end, f.getlist('property_id'),
                                               f['fingerprint'], f['request_key'])
        return page(request, db, 'drafts_created', created=items)
    except (ValueError, KeyError) as exc:
        return selection_page(request, db, f, str(exc))


@router.post('/settlements/individual-preview')
async def settlement_individual_preview(request: Request, db=Depends(get_db)):
    try:
        _, owner, start, end, properties, excluded = await selection(request, db)
        view = settlements.preview(db, owner, start, end, properties, excluded)
        return page(request, db, "preview", view=view)
    except (ValueError, KeyError) as exc:
        return selection_page(request, db, {}, str(exc))


@router.post("/settlements/draft")
async def settlement_draft(request: Request, db=Depends(get_db)):
    try:
        f, owner, start, end, properties, excluded = await selection(request, db)
        item = settlements.save_draft(db, owner_id=owner, start=start, end=end, property_ids=properties,
            excluded=excluded, expected=f["fingerprint"], request_key=f["request_key"])
        return RedirectResponse(f"/settlements/{item.id}", 303)
    except (ValueError, KeyError) as exc:
        return selection_page(request, db, {}, str(exc))


@router.get("/settlements/terms")
def terms_page(request: Request, db=Depends(get_db)):
    return page(request, db, "terms", terms=list(db.scalars(select(ManagementFeeTerms))))


@router.post("/settlements/terms")
async def terms_create(request: Request, db=Depends(get_db)):
    f = await request.form()
    try:
        settlements.add_terms(db, property_id=int(f["property_id"]), owner_id=int(f["owner_id"]),
            effective_from=date.fromisoformat(f["effective_from"]),
            effective_until=date.fromisoformat(f["effective_until"]) if f.get("effective_until") else None,
            percentage=f["percentage"], vat_rate=f["vat_rate"], withholding_rate=f["withholding_rate"])
        return RedirectResponse("/settlements/terms", 303)
    except (ValueError, KeyError) as exc:
        return page(request, db, "terms", error=str(exc), terms=list(db.scalars(select(ManagementFeeTerms))))


@router.get("/settlements/custody")
def custody_page(request: Request, db=Depends(get_db)):
    return page(request, db, "custody", payments=list(db.scalars(select(Payment).where(Payment.lifecycle == "posted", Payment.direction == "receipt"))))


@router.get("/settlements/ownership")
def ownership_page(request: Request, db=Depends(get_db)):
    return page(request, db, "ownership")


@router.post("/settlements/ownership")
async def ownership_version(request: Request, db=Depends(get_db)):
    f = await request.form()
    try:
        shares = [(int(key[6:]), value) for key,value in f.items() if key.startswith("share_") and value.strip()]
        settlements.version_ownership(db, int(f["property_id"]), date.fromisoformat(f["effective_from"]), shares)
        return RedirectResponse("/settlements/ownership", 303)
    except (ValueError, KeyError) as exc:
        return page(request, db, "ownership", error=str(exc))


@router.post("/settlements/custody")
async def custody_save(request: Request, db=Depends(get_db)):
    f = await request.form()
    try:
        settlements.set_custody(db, int(f["payment_id"]), actor=f["actor"], owner_id=int(f["owner_id"]) if f.get("owner_id") else None)
        return RedirectResponse("/settlements/custody", 303)
    except (ValueError, KeyError) as exc:
        return page(request, db, "custody", error=str(exc), payments=list(db.scalars(select(Payment).where(Payment.direction == "receipt"))))


def detail(request, db, item, error=None):
    payouts = list(db.scalars(select(OwnerPayout).where(OwnerPayout.settlement_id == item.id)))
    paid = sum((p.amount for p in payouts), Decimal("0.00"))
    due = Decimal(item.snapshot["totals"]["payout_due"])
    return page(request, db, "settlement", item=item, view=item.snapshot, error=error, payouts=payouts,
        paid=paid, remaining=max(Decimal("0.00"), due-paid),
        payment_status="Saldo a favor del gestor" if Decimal(item.snapshot['totals']['carry_forward']) < 0 else "Sin transferencia del gestor" if due == 0 else "Pagada" if paid == due else "Parcialmente pagada" if paid > 0 else "Pendiente de pago",
        accounts=list(db.scalars(select(OwnerBankAccount).where(OwnerBankAccount.owner_id == item.owner_id,
            OwnerBankAccount.active == True, OwnerBankAccount.receives_settlements == True))))


@router.get("/settlements/{settlement_id}")
def settlement_detail(request: Request, settlement_id: int, db=Depends(get_db)):
    item = db.get(OwnerSettlement, settlement_id)
    if item is None:
        raise HTTPException(404)
    return detail(request, db, item)


@router.post("/settlements/{settlement_id}/close")
async def settlement_close(request: Request, settlement_id: int, db=Depends(get_db)):
    f = await request.form()
    try:
        settlements.close(db, settlement_id, f["fingerprint"])
        return RedirectResponse(f"/settlements/{settlement_id}", 303)
    except (ValueError, KeyError) as exc:
        item = db.get(OwnerSettlement, settlement_id)
        if item is None:
            raise HTTPException(404)
        return detail(request, db, item, str(exc))


@router.post("/settlements/{settlement_id}/payout")
async def settlement_payout(request: Request, settlement_id: int, db=Depends(get_db)):
    f = await request.form()
    try:
        settlements.payout(db, settlement_id, amount=f["amount"], effective_date=date.fromisoformat(f["effective_date"]),
            bank_account_id=int(f["bank_account_id"]), method="bank_transfer", request_key=f["request_key"], reference=f.get("reference"))
        return RedirectResponse(f"/settlements/{settlement_id}", 303)
    except (ValueError, KeyError) as exc:
        item = db.get(OwnerSettlement, settlement_id)
        if item is None:
            raise HTTPException(404)
        return detail(request, db, item, str(exc))


@router.post('/settlements/{settlement_id}/documents')
def settlement_pdf_create(request: Request, settlement_id: int, db=Depends(get_db)):
    from backend.services.settlement_document_service import SettlementDocumentService, storage_for
    try:
        artifact = SettlementDocumentService(storage_for(db)).generate(db, settlement_id)
        return RedirectResponse(f"/settlements/{settlement_id}/documents/{artifact['version']}", 303)
    except ValueError as exc:
        item = db.get(OwnerSettlement, settlement_id)
        if item is None:
            raise HTTPException(404)
        return detail(request, db, item, str(exc))


@router.get('/settlements/{settlement_id}/documents/{version}')
def settlement_pdf_download(settlement_id: int, version: int, db=Depends(get_db)):
    from backend.services.settlement_document_service import SettlementDocumentService, storage_for
    try:
        artifact, path = SettlementDocumentService(storage_for(db)).download(db, settlement_id, version)
    except ValueError:
        raise HTTPException(404, 'Documento no disponible.')
    return FileResponse(path, media_type='application/pdf',
                        filename=f'liquidacion-{settlement_id}-v{artifact["version"]}.pdf',
                        headers={'Cache-Control':'private, no-store', 'X-Robots-Tag':'noindex, nofollow',
                                 'X-Content-Type-Options':'nosniff'})
