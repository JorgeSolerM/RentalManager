from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.iban import is_valid_iban, normalize_iban
from backend.core.operation_result import OperationResult
from backend.models.owner import Owner
from backend.models.owner_bank_account import OwnerBankAccount
from backend.models.property import Property
from backend.models.property_ownership import PropertyOwnership
from backend.repositories.owner_repository import OwnerRepository


class OwnerService:
    def __init__(self):
        self.repository = OwnerRepository()

    @staticmethod
    def _optional(value: str | None) -> str | None:
        normalized = " ".join((value or "").split())
        return normalized or None

    def save_owner(self, db: Session, owner_id: int | None, **values):
        owner = self.repository.get(db, owner_id) if owner_id else Owner()
        if owner is None:
            db.rollback()
            return OperationResult(False, "owner_not_found")
        legal_name = self._optional(values.get("legal_name"))
        if not legal_name:
            db.rollback()
            return OperationResult(False, "owner_legal_name_required", owner)
        owner.legal_name = legal_name
        owner.display_name = self._optional(values.get("display_name"))
        owner.tax_id = self._optional(values.get("tax_id"))
        owner.email = self._optional(values.get("email"))
        if owner.email:
            owner.email = owner.email.lower()
        owner.phone = self._optional(values.get("phone"))
        owner.address_line = self._optional(values.get("address_line"))
        owner.postal_code = self._optional(values.get("postal_code"))
        owner.city = self._optional(values.get("city"))
        owner.province = self._optional(values.get("province"))
        country = self._optional(values.get("country"))
        if country and len(country) != 2:
            db.rollback()
            return OperationResult(False, "owner_country_invalid", owner)
        owner.country = country.upper() if country else None
        owner.notes = self._optional(values.get("notes"))
        owner.active = bool(values.get("active", False))
        try:
            db.add(owner)
            db.commit()
            return OperationResult(True, "owner_saved", owner)
        except IntegrityError:
            db.rollback()
            return OperationResult(False, "owner_invalid", owner)

    def save_account(self, db: Session, owner_id: int, account_id: int | None, **values):
        owner = self.repository.get(db, owner_id)
        if owner is None:
            db.rollback()
            return OperationResult(False, "owner_not_found")
        account = self.repository.get_account(db, account_id) if account_id else OwnerBankAccount(owner_id=owner_id)
        if account is None or account.owner_id != owner_id:
            db.rollback()
            return OperationResult(False, "owner_account_not_found")
        holder = self._optional(values.get("account_holder_name"))
        iban = normalize_iban(values.get("iban"))
        if not holder:
            db.rollback()
            return OperationResult(False, "owner_account_holder_required", account)
        if iban is None or not is_valid_iban(iban):
            db.rollback()
            return OperationResult(False, "owner_account_iban_invalid", account)
        active = bool(values.get("active", False))
        receives_rent = bool(values.get("receives_rent", False))
        if account.id and self.repository.account_in_active_ownership(db, account.id):
            if not active or not receives_rent:
                db.rollback()
                return OperationResult(False, "owner_account_in_use", account)
        account.account_holder_name = holder
        account.iban = iban
        account.bic = (self._optional(values.get("bic")) or "").replace(" ", "").upper() or None
        if account.bic and (len(account.bic) not in {8, 11} or not account.bic.isalnum()):
            db.rollback()
            return OperationResult(False, "owner_account_bic_invalid", account)
        account.alias = self._optional(values.get("alias"))
        account.currency = "EUR"
        account.active = active
        account.receives_rent = receives_rent
        account.receives_settlements = bool(values.get("receives_settlements", False))
        try:
            db.add(account)
            db.commit()
            return OperationResult(True, "owner_account_saved", account)
        except IntegrityError:
            db.rollback()
            return OperationResult(False, "owner_account_duplicate", account)

    @staticmethod
    def _percentage(value) -> Decimal | None:
        if isinstance(value, float):
            return None
        try:
            percentage = Decimal(value).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return percentage if Decimal("0") < percentage <= Decimal("100") else None

    def save_ownership(
        self,
        db: Session,
        owner_id: int,
        ownership_id: int | None,
        *,
        property_id: int,
        ownership_percentage,
        rent_bank_account_id: int | None,
        effective_from: date | None,
        effective_until: date | None,
    ):
        owner = self.repository.get(db, owner_id)
        property_obj = db.get(Property, property_id)
        if owner is None:
            db.rollback(); return OperationResult(False, "owner_not_found")
        if property_obj is None:
            db.rollback(); return OperationResult(False, "property_not_found")
        percentage = self._percentage(ownership_percentage)
        if percentage is None:
            db.rollback(); return OperationResult(False, "ownership_percentage_invalid")
        if effective_from and effective_until and effective_until < effective_from:
            db.rollback(); return OperationResult(False, "ownership_dates_invalid")
        ownership = self.repository.get_ownership(db, ownership_id) if ownership_id else None
        if ownership_id and (ownership is None or ownership.owner_id != owner_id):
            db.rollback(); return OperationResult(False, "ownership_not_found")
        if ownership is None:
            if self.repository.active_ownership(db, property_id, owner_id):
                db.rollback(); return OperationResult(False, "ownership_exists")
            ownership = PropertyOwnership(owner_id=owner_id, property_id=property_id, active=True)
        elif ownership.property_id != property_id:
            db.rollback(); return OperationResult(False, "ownership_property_immutable")
        account = None
        if rent_bank_account_id:
            account = self.repository.get_account(db, rent_bank_account_id)
            if account is None or account.owner_id != owner_id:
                db.rollback(); return OperationResult(False, "ownership_account_wrong_owner")
            if not account.active or not account.receives_rent:
                db.rollback(); return OperationResult(False, "ownership_account_not_eligible")
        ownership.ownership_percentage = percentage
        ownership.rent_bank_account_id = account.id if account else None
        ownership.effective_from = effective_from
        ownership.effective_until = effective_until
        ownership.active = True
        try:
            db.add(ownership)
            db.commit()
            return OperationResult(True, "ownership_saved", ownership)
        except IntegrityError:
            db.rollback()
            return OperationResult(False, "ownership_invalid", ownership)

    def deactivate_ownership(self, db: Session, owner_id: int, ownership_id: int):
        ownership = self.repository.get_ownership(db, ownership_id)
        if ownership is None or ownership.owner_id != owner_id:
            db.rollback(); return OperationResult(False, "ownership_not_found")
        ownership.active = False
        if ownership.effective_until is None:
            ownership.effective_until = date.today()
        db.add(ownership)
        db.commit()
        return OperationResult(True, "ownership_deactivated", ownership)

    def delete_owner(self, db: Session, owner_id: int):
        owner = self.repository.get(db, owner_id)
        if owner is None:
            db.rollback(); return OperationResult(False, "owner_not_found")
        if owner.bank_accounts or owner.property_ownerships:
            db.rollback(); return OperationResult(False, "owner_has_relations")
        db.delete(owner)
        db.commit()
        return OperationResult(True, "owner_deleted")

    def ownership_total(self, db: Session, property_id: int) -> Decimal:
        return sum(
            (item.ownership_percentage for item in self.repository.active_property_total(db, property_id)),
            Decimal("0.00"),
        )
