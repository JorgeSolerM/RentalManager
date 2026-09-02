from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.repositories.property_repository import PropertyRepository
from backend.services.owner_service import OwnerService


router = APIRouter(prefix="/owners")
templates = Jinja2Templates(directory="backend/templates")
service = OwnerService()
property_repository = PropertyRepository()


@router.get("")
def list_owners(request: Request, db: Session = Depends(get_db)):
    return templates.TemplateResponse(
        request=request,
        name="pages/owners.html",
        context={"request": request, "owners": service.repository.list(db)},
    )


@router.get("/new")
def new_owner(request: Request):
    return templates.TemplateResponse(
        request=request, name="pages/owner_form.html", context={"request": request, "owner": None}
    )


@router.get("/{owner_id}")
def owner_detail(request: Request, owner_id: int, db: Session = Depends(get_db)):
    owner = service.repository.get(db, owner_id)
    if owner is None:
        raise HTTPException(404, "Propietario no encontrado")
    properties = property_repository.get_all(db)
    eligible_accounts = [item for item in owner.bank_accounts if item.active and item.receives_rent]
    suggested_account_id = eligible_accounts[0].id if len(eligible_accounts) == 1 else None
    totals = {
        item.property_id: service.ownership_total(db, item.property_id)
        for item in owner.property_ownerships if item.active
    }
    return templates.TemplateResponse(
        request=request,
        name="pages/owner_detail.html",
        context={
            "request": request, "owner": owner, "properties": properties,
            "eligible_accounts": eligible_accounts,
            "suggested_account_id": suggested_account_id, "ownership_totals": totals,
        },
    )


@router.get("/{owner_id}/edit")
def edit_owner(request: Request, owner_id: int, db: Session = Depends(get_db)):
    owner = service.repository.get(db, owner_id)
    if owner is None:
        raise HTTPException(404, "Propietario no encontrado")
    return templates.TemplateResponse(
        request=request, name="pages/owner_form.html", context={"request": request, "owner": owner}
    )


def _owner_values(legal_name, display_name, tax_id, email, phone, address_line,
                  postal_code, city, province, country, notes, active):
    return dict(legal_name=legal_name, display_name=display_name, tax_id=tax_id,
                email=email, phone=phone, address_line=address_line,
                postal_code=postal_code, city=city, province=province,
                country=country, notes=notes, active=active)


@router.post("/create")
def create_owner(legal_name: str = Form(...), display_name: str = Form(""), tax_id: str = Form(""),
                 email: str = Form(""), phone: str = Form(""), address_line: str = Form(""),
                 postal_code: str = Form(""), city: str = Form(""), province: str = Form(""),
                 country: str = Form(""), notes: str = Form(""), active: bool = Form(False),
                 db: Session = Depends(get_db)):
    result = service.save_owner(db, None, **_owner_values(legal_name, display_name, tax_id, email, phone, address_line, postal_code, city, province, country, notes, active))
    target = f"/owners/{result.data.id}?success=owner_saved" if result.success else f"/owners/new?error={result.message}"
    return RedirectResponse(target, 303)


@router.post("/{owner_id}/update")
def update_owner(owner_id: int, legal_name: str = Form(...), display_name: str = Form(""), tax_id: str = Form(""),
                 email: str = Form(""), phone: str = Form(""), address_line: str = Form(""),
                 postal_code: str = Form(""), city: str = Form(""), province: str = Form(""),
                 country: str = Form(""), notes: str = Form(""), active: bool = Form(False),
                 db: Session = Depends(get_db)):
    result = service.save_owner(db, owner_id, **_owner_values(legal_name, display_name, tax_id, email, phone, address_line, postal_code, city, province, country, notes, active))
    return RedirectResponse(f"/owners/{owner_id}?{'success=owner_saved' if result.success else 'error='+result.message}", 303)


@router.post("/{owner_id}/delete")
def delete_owner(owner_id: int, db: Session = Depends(get_db)):
    result = service.delete_owner(db, owner_id)
    return RedirectResponse("/owners?success=owner_deleted" if result.success else f"/owners/{owner_id}?error={result.message}", 303)


@router.post("/{owner_id}/accounts")
@router.post("/{owner_id}/accounts/{account_id}")
def save_account(owner_id: int, account_id: int | None = None,
                 account_holder_name: str = Form(...), iban: str = Form(...), bic: str = Form(""),
                 alias: str = Form(""), active: bool = Form(False), receives_rent: bool = Form(False),
                 receives_settlements: bool = Form(False), db: Session = Depends(get_db)):
    result = service.save_account(db, owner_id, account_id, account_holder_name=account_holder_name,
                                  iban=iban, bic=bic, alias=alias, active=active,
                                  receives_rent=receives_rent, receives_settlements=receives_settlements)
    return RedirectResponse(f"/owners/{owner_id}?{'success=owner_account_saved' if result.success else 'error='+result.message}", 303)


@router.post("/{owner_id}/ownerships")
@router.post("/{owner_id}/ownerships/{ownership_id}")
def save_ownership(owner_id: int, ownership_id: int | None = None,
                   property_id: int = Form(...), ownership_percentage: str = Form(...),
                   rent_bank_account_id: int | None = Form(None), effective_from: date | None = Form(None),
                   effective_until: date | None = Form(None), db: Session = Depends(get_db)):
    result = service.save_ownership(db, owner_id, ownership_id, property_id=property_id,
                                    ownership_percentage=ownership_percentage,
                                    rent_bank_account_id=rent_bank_account_id,
                                    effective_from=effective_from, effective_until=effective_until)
    return RedirectResponse(f"/owners/{owner_id}?{'success=ownership_saved' if result.success else 'error='+result.message}", 303)


@router.post("/{owner_id}/ownerships/{ownership_id}/deactivate")
def deactivate_ownership(owner_id: int, ownership_id: int, db: Session = Depends(get_db)):
    result = service.deactivate_ownership(db, owner_id, ownership_id)
    return RedirectResponse(f"/owners/{owner_id}?{'success=ownership_deactivated' if result.success else 'error='+result.message}", 303)
