from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models.booking import Booking
from backend.models.booking_party import BookingParty
from backend.models.person import Person


class BookingPartyRepository:
    def list_for_booking(self, db: Session, booking_id: int) -> list[BookingParty]:
        return list(db.scalars(select(BookingParty).options(selectinload(BookingParty.person)).where(BookingParty.booking_id == booking_id).order_by(BookingParty.id)))

    def get(self, db: Session, party_id: int) -> BookingParty | None:
        return db.get(BookingParty, party_id)

    def booking_exists(self, db: Session, booking_id: int) -> bool:
        return db.get(Booking, booking_id) is not None

    def person_exists(self, db: Session, person_id: int) -> bool:
        return db.get(Person, person_id) is not None
