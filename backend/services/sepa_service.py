from datetime import date
from sqlalchemy import update

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.iban import is_valid_iban, normalize_iban
from backend.core.operation_result import OperationResult
from backend.core.sepa import is_valid_bic, is_valid_sepa_identifier, normalize_bic, normalize_sepa_identifier
from backend.models.booking_sepa_mandate import BookingSepaMandate
from backend.models.owner_bank_account import OwnerBankAccount
from backend.models.person import Person
from backend.models.sepa_creditor_profile import SepaCreditorProfile
from backend.models.sepa_mandate import SEPA_MANDATE_STATUSES, SEPA_MANDATE_TYPES, SepaMandate
from backend.repositories.sepa_repository import SepaRepository


class SepaService:
    def generate_reference(self, db: Session, creditor_profile_id: int):
        """Consume a number atomically, including when the form is abandoned.

        UPDATE is the first statement: SQLite serializes competing writers.
        Existing manually entered HSI references are skipped under that lock.
        """
        try:
            while True:
                number = db.scalar(update(SepaCreditorProfile).where(
                    SepaCreditorProfile.id == creditor_profile_id,
                    SepaCreditorProfile.active.is_(True),
                    SepaCreditorProfile.mandate_reference_counter < 999999999,
                ).values(mandate_reference_counter=SepaCreditorProfile.mandate_reference_counter + 1)
                  .returning(SepaCreditorProfile.mandate_reference_counter))
                if number is None:
                    db.rollback()
                    return OperationResult(False, "sepa_reference_unavailable")
                reference = f"HSI{number:09d}"
                if not self.repository.reference_exists(db, creditor_profile_id, reference):
                    db.commit()
                    return OperationResult(True, "sepa_reference_generated", reference)
        except Exception:
            db.rollback()
            raise

    def __init__(self):
        self.repository = SepaRepository()

    @staticmethod
    def _text(value: str | None) -> str | None:
        result = " ".join((value or "").split())
        return result or None

    def save_profile(self, db: Session, profile_id: int | None, *, display_name: str, creditor_name: str,
                     creditor_identifier: str, owner_id: int | None, bank_account_id: int,
                     scheme: str, active: bool, notes: str | None):
        account = db.get(OwnerBankAccount, bank_account_id)
        if account is None:
            db.rollback(); return OperationResult(False, "sepa_account_not_found")
        if not account.active or not account.receives_rent:
            db.rollback(); return OperationResult(False, "sepa_account_not_eligible")
        if owner_id is not None and account.owner_id != owner_id:
            db.rollback(); return OperationResult(False, "sepa_account_wrong_owner")
        identifier = normalize_sepa_identifier(creditor_identifier)
        if not is_valid_sepa_identifier(identifier):
            db.rollback(); return OperationResult(False, "sepa_creditor_identifier_invalid")
        if scheme != "CORE":
            db.rollback(); return OperationResult(False, "sepa_scheme_invalid")
        display = self._text(display_name); creditor = self._text(creditor_name)
        if not display or not creditor:
            db.rollback(); return OperationResult(False, "sepa_profile_required_fields")
        profile = self.repository.get_profile(db, profile_id) if profile_id else SepaCreditorProfile()
        if profile is None:
            db.rollback(); return OperationResult(False, "sepa_profile_not_found")
        profile.display_name = display; profile.creditor_name = creditor
        profile.creditor_identifier = identifier; profile.owner_id = owner_id
        profile.bank_account_id = account.id; profile.scheme = "CORE"
        profile.active = active; profile.notes = self._text(notes)
        try:
            db.add(profile); db.commit()
            return OperationResult(True, "sepa_profile_saved", profile)
        except IntegrityError:
            db.rollback(); return OperationResult(False, "sepa_profile_account_conflict", profile)

    def save_mandate(self, db: Session, mandate_id: int | None, *, creditor_profile_id: int,
                     person_id: int | None, debtor_name: str, debtor_iban: str, debtor_bic: str | None,
                     mandate_reference: str, signature_date: date, mandate_type: str, status: str,
                     amendment_indicator: bool, active_from: date | None, cancelled_at: date | None,
                     notes: str | None):
        profile = self.repository.get_profile(db, creditor_profile_id)
        if profile is None:
            db.rollback(); return OperationResult(False, "sepa_profile_not_found")
        if person_id is not None and db.get(Person, person_id) is None:
            db.rollback(); return OperationResult(False, "person_not_found")
        name = self._text(debtor_name); iban = normalize_iban(debtor_iban)
        bic = normalize_bic(debtor_bic); reference = (mandate_reference or "").strip()
        if not name or not reference or len(reference) > 35:
            db.rollback(); return OperationResult(False, "sepa_mandate_required_fields")
        if not is_valid_iban(iban):
            db.rollback(); return OperationResult(False, "sepa_debtor_iban_invalid")
        if not is_valid_bic(bic):
            db.rollback(); return OperationResult(False, "sepa_debtor_bic_invalid")
        if mandate_type not in SEPA_MANDATE_TYPES or status not in SEPA_MANDATE_STATUSES:
            db.rollback(); return OperationResult(False, "sepa_mandate_state_invalid")
        mandate = self.repository.get_mandate(db, mandate_id) if mandate_id else SepaMandate()
        if mandate is None:
            db.rollback(); return OperationResult(False, "sepa_mandate_not_found")
        if mandate.id and mandate.status != "draft" and (
            mandate.mandate_reference != reference or mandate.creditor_profile_id != profile.id
            or status == "draft"
        ):
            db.rollback(); return OperationResult(False, "sepa_reference_immutable")
        if self.repository.reference_exists(db, profile.id, reference, mandate.id):
            db.rollback(); return OperationResult(False, "sepa_mandate_reference_exists")
        mandate.creditor_profile_id = profile.id; mandate.person_id = person_id
        mandate.debtor_name = name; mandate.debtor_iban = iban; mandate.debtor_bic = bic
        mandate.mandate_reference = reference; mandate.signature_date = signature_date
        mandate.mandate_type = mandate_type; mandate.status = status
        mandate.amendment_indicator = amendment_indicator; mandate.active_from = active_from
        mandate.cancelled_at = cancelled_at; mandate.notes = self._text(notes)
        try:
            db.add(mandate); db.commit()
            return OperationResult(True, "sepa_mandate_saved", mandate)
        except IntegrityError:
            db.rollback(); return OperationResult(False, "sepa_mandate_invalid", mandate)

    def link_booking(self, db: Session, booking_id: int, mandate_id: int):
        booking = self.repository.get_booking(db, booking_id)
        mandate = self.repository.get_mandate(db, mandate_id)
        if booking is None:
            db.rollback(); return OperationResult(False, "not_found")
        if mandate is None:
            db.rollback(); return OperationResult(False, "sepa_mandate_not_found")
        if mandate.status != "active" or not mandate.creditor_profile.active:
            db.rollback(); return OperationResult(False, "sepa_mandate_not_active")
        compatible_ids = {item.id for item in self.repository.compatible_profiles(db, booking)}
        if mandate.creditor_profile_id not in compatible_ids:
            db.rollback(); return OperationResult(False, "sepa_mandate_property_incompatible")
        current = self.repository.active_binding(db, booking_id)
        if current:
            current.active = False
            db.flush()
        binding = self.repository.binding(db, booking_id, mandate_id)
        if binding is None:
            binding = BookingSepaMandate(booking_id=booking_id, mandate_id=mandate_id)
        binding.active = True
        try:
            db.add(binding); db.commit()
            return OperationResult(True, "sepa_mandate_linked", binding)
        except IntegrityError:
            db.rollback(); return OperationResult(False, "sepa_mandate_link_invalid")

    def unlink_booking(self, db: Session, booking_id: int):
        binding = self.repository.active_binding(db, booking_id)
        if binding is None:
            db.rollback(); return OperationResult(False, "sepa_booking_mandate_missing")
        binding.active = False; db.add(binding); db.commit()
        return OperationResult(True, "sepa_mandate_unlinked", binding)
