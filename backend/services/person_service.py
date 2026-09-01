from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.business_time import business_today
from backend.core.operation_result import OperationResult
from backend.core.iban import is_valid_iban, normalize_iban
from backend.models.person import Person
from backend.repositories.person_repository import PersonRepository


class PersonService:
    def __init__(self):
        self.repository = PersonRepository()

    @staticmethod
    def _optional(value: str | None) -> str | None:
        normalized = " ".join((value or "").split())
        return normalized or None

    def populate(self, person: Person, **values) -> str | None:
        full_name = self._optional(values.get("full_name"))
        if not full_name:
            return "person_full_name_required"
        birth_date = values.get("birth_date")
        if birth_date and birth_date > business_today():
            return "person_birth_date_future"
        document_type = self._optional(values.get("document_type"))
        if document_type and document_type not in {"dni", "nie", "passport", "other"}:
            return "person_document_type_invalid"
        verification = values.get("verification_status", "unverified")
        if verification not in {"unverified", "verified"}:
            return "person_verification_invalid"
        person.full_name = full_name
        person.display_name = self._optional(values.get("display_name"))
        person.phone = self._optional(values.get("phone"))
        email = self._optional(values.get("email"))
        person.email = email.lower() if email else None
        iban = normalize_iban(values.get("iban"))
        if iban is not None and not is_valid_iban(iban):
            return "person_iban_invalid"
        person.iban = iban
        person.document_type = document_type
        document = self._optional(values.get("document_number"))
        person.document_number = document.upper() if document else None
        for field in ("document_issuer_country", "nationality", "country"):
            country = self._optional(values.get(field))
            if country and len(country) != 2:
                return "person_country_code_invalid"
            setattr(person, field, country.upper() if country else None)
        person.birth_date = birth_date
        for field in ("address_line", "postal_code", "city", "province", "notes"):
            setattr(person, field, self._optional(values.get(field)))
        person.active = bool(values.get("active", False))
        person.verification_status = verification
        return None

    def save(self, db: Session, person_id: int | None, **values) -> OperationResult[Person]:
        person = self.repository.get(db, person_id) if person_id else Person(source="manual")
        if person is None:
            db.rollback(); return OperationResult(False, "person_not_found")
        error = self.populate(person, **values)
        if error:
            db.rollback(); return OperationResult(False, error, person)
        try:
            db.add(person); db.commit(); return OperationResult(True, data=person)
        except IntegrityError:
            db.rollback(); return OperationResult(False, "person_invalid")

    def create_unclassified_in_session(self, db: Session, full_name: str) -> Person:
        person = Person(full_name=" ".join(full_name.split()), display_name=" ".join(full_name.split()), active=True, verification_status="unverified", source="manual")
        db.add(person); db.flush(); return person

    def delete(self, db: Session, person_id: int) -> OperationResult[None]:
        person = self.repository.get(db, person_id)
        if person is None:
            db.rollback(); return OperationResult(False, "person_not_found")
        if self.repository.is_linked(db, person_id):
            db.rollback(); return OperationResult(False, "person_has_booking_parties")
        db.delete(person); db.commit(); return OperationResult(True, "person_deleted")
