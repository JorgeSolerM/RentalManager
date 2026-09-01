from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from backend.models.booking_party import BookingParty
from backend.models.booking import Booking
from backend.models.room import Room
from backend.models.person import Person


class PersonRepository:
    def get(self, db: Session, person_id: int) -> Person | None:
        return db.scalar(select(Person).options(selectinload(Person.booking_parties).selectinload(BookingParty.booking)).where(Person.id == person_id))

    def list(self, db: Session, search: str = "") -> list[Person]:
        statement = (
            select(Person)
            .options(
                selectinload(Person.booking_parties)
                .selectinload(BookingParty.booking)
                .selectinload(Booking.room)
                .selectinload(Room.property)
            )
            .order_by(func.lower(Person.full_name), Person.id)
        )
        if search.strip():
            term = f"%{search.strip().lower()}%"
            statement = statement.where(or_(func.lower(Person.full_name).like(term), func.lower(func.coalesce(Person.email, "")).like(term), func.lower(func.coalesce(Person.document_number, "")).like(term)))
        return list(db.scalars(statement))

    def is_linked(self, db: Session, person_id: int) -> bool:
        return db.scalar(select(BookingParty.id).where(BookingParty.person_id == person_id).limit(1)) is not None
