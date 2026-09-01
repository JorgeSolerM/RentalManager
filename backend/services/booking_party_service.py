from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.models.booking_party import BOOKING_PARTY_ROLES, BookingParty
from backend.repositories.booking_party_repository import BookingPartyRepository


class BookingPartyService:
    def __init__(self):
        self.repository = BookingPartyRepository()

    def add(self, db: Session, booking_id: int, person_id: int, role: str) -> OperationResult[BookingParty]:
        if role not in BOOKING_PARTY_ROLES:
            db.rollback(); return OperationResult(False, "booking_party_role_invalid")
        if not self.repository.booking_exists(db, booking_id):
            db.rollback(); return OperationResult(False, "booking_not_found")
        if not self.repository.person_exists(db, person_id):
            db.rollback(); return OperationResult(False, "person_not_found")
        try:
            party = BookingParty(booking_id=booking_id, person_id=person_id, role=role)
            db.add(party); db.commit(); return OperationResult(True, data=party)
        except IntegrityError:
            db.rollback(); return OperationResult(False, "booking_party_duplicate")

    def remove(self, db: Session, party_id: int, booking_id: int | None = None) -> OperationResult[None]:
        party = self.repository.get(db, party_id)
        if party is None:
            db.rollback(); return OperationResult(False, "booking_party_not_found")
        if booking_id is not None and party.booking_id != booking_id:
            db.rollback(); return OperationResult(False, "booking_party_mismatch")
        db.delete(party); db.commit(); return OperationResult(True, "booking_party_removed")
