from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from backend.models.booking import Booking
from backend.models.person import Person
from backend.models.booking_sepa_mandate import BookingSepaMandate
from backend.services.financial_transaction import financial_transaction

from backend.core.operation_result import OperationResult
from backend.models.booking_party import BOOKING_PARTY_ROLES, BookingParty
from backend.repositories.booking_party_repository import BookingPartyRepository


class BookingPartyService:
    def view(self, db, booking_id):
        rows = list(db.scalars(select(BookingParty).options(joinedload(BookingParty.person)).where(BookingParty.booking_id == booking_id).order_by(BookingParty.person_id, BookingParty.role)))
        payers = {r.person_id for r in rows if r.role == 'payer'}
        bindings = list(db.scalars(select(BookingSepaMandate).where(BookingSepaMandate.booking_id == booking_id, BookingSepaMandate.active == True)))
        warning = any(b.mandate.person_id is None or b.mandate.person_id not in payers for b in bindings)
        return {'parties': [{'id': r.id, 'person_id': r.person_id, 'person_name': r.person.display_name or r.person.full_name, 'role': r.role} for r in rows],
                'warning': 'Revisar configuración SEPA: el mandato vinculado no identifica a un responsable de pago actual. No se ha modificado el mandato.' if warning else None}

    def change_functions(self, db, booking_id, person_id, roles, *, mode='replace', confirm_sepa_review=False):
        """Replace one person's role set under a write lock; preserve unchanged IDs.

        BookingParty currently has no validity/history columns: removed functions
        are deleted, not soft-deleted. Person, Booking and financial data are untouched.
        """
        desired = set(roles)
        if mode not in {'add', 'replace', 'unlink'}:
            raise ValueError('Operación no válida.')
        if mode != 'unlink' and (not desired or not desired <= set(BOOKING_PARTY_ROLES)):
            raise ValueError('Selecciona al menos una función para el inquilino.')
        if 'unclassified' in desired and len(desired) > 1:
            raise ValueError('Sin clasificar no puede combinarse con funciones conocidas.')
        with financial_transaction(db):
            if db.get(Booking, booking_id) is None or db.get(Person, person_id) is None:
                raise ValueError('Reserva o persona no encontrada.')
            rows = list(db.scalars(select(BookingParty).where(BookingParty.booking_id == booking_id)))
            own = {r.role: r for r in rows if r.person_id == person_id}
            if mode == 'replace' and not own:
                raise ValueError('La persona ya no está vinculada a esta reserva.')
            if mode == 'unlink':
                target = set()
            elif mode == 'add':
                target = desired | set(own)
            else:
                target = desired
            if target - {'unclassified'}:
                target.discard('unclassified')
            old_payers = {r.person_id for r in rows if r.role == 'payer'}
            new_payers = old_payers - {person_id}
            if 'payer' in target:
                new_payers.add(person_id)
            if old_payers != new_payers:
                bindings = list(db.scalars(select(BookingSepaMandate).where(BookingSepaMandate.booking_id == booking_id, BookingSepaMandate.active == True)))
                if any(b.mandate.person_id is None or b.mandate.person_id not in new_payers for b in bindings) and not confirm_sepa_review:
                    raise ValueError('sepa_review_required')
            for role, row in own.items():
                if role not in target:
                    db.delete(row)
            for role in sorted(target - set(own)):
                db.add(BookingParty(booking_id=booking_id, person_id=person_id, role=role))
        return self.view(db, booking_id)

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
        # Compatibility endpoint: it cannot acknowledge the new SEPA review UI.
        # Do not let it silently bypass the grouped editor's safeguard.
        if party.role == 'payer':
            binding = db.scalar(select(BookingSepaMandate).where(
                BookingSepaMandate.booking_id == party.booking_id,
                BookingSepaMandate.active == True,
            ))
            if binding is not None:
                db.rollback()
                return OperationResult(False, "Revisa el mandato SEPA y utiliza Editar funciones para confirmar el cambio.")
        db.delete(party); db.commit(); return OperationResult(True, "booking_party_removed")
