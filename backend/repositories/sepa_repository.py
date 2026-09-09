from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.models.booking import Booking
from backend.models.booking_sepa_mandate import BookingSepaMandate
from backend.models.room import Room
from backend.models.property import Property
from backend.models.property_ownership import PropertyOwnership
from backend.models.sepa_creditor_profile import SepaCreditorProfile
from backend.models.sepa_mandate import SepaMandate


class SepaRepository:
    def get_profile(self, db: Session, profile_id: int) -> SepaCreditorProfile | None:
        return db.scalar(
            select(SepaCreditorProfile)
            .options(joinedload(SepaCreditorProfile.bank_account), selectinload(SepaCreditorProfile.mandates))
            .where(SepaCreditorProfile.id == profile_id)
        )

    def active_profiles(self, db: Session) -> list[SepaCreditorProfile]:
        return list(db.scalars(
            select(SepaCreditorProfile)
            .options(joinedload(SepaCreditorProfile.bank_account))
            .where(SepaCreditorProfile.active.is_(True))
            .order_by(SepaCreditorProfile.display_name, SepaCreditorProfile.id)
        ).unique())

    def get_mandate(self, db: Session, mandate_id: int) -> SepaMandate | None:
        return db.scalar(
            select(SepaMandate)
            .options(joinedload(SepaMandate.creditor_profile).joinedload(SepaCreditorProfile.bank_account), joinedload(SepaMandate.person))
            .where(SepaMandate.id == mandate_id)
        )

    def reference_exists(self, db: Session, profile_id: int, reference: str, exclude_id: int | None = None) -> bool:
        statement = select(SepaMandate.id).where(
            SepaMandate.creditor_profile_id == profile_id,
            SepaMandate.mandate_reference == reference,
        )
        if exclude_id is not None:
            statement = statement.where(SepaMandate.id != exclude_id)
        return db.scalar(statement.limit(1)) is not None

    def get_booking(self, db: Session, booking_id: int) -> Booking | None:
        return db.scalar(
            select(Booking)
            .options(
                joinedload(Booking.room).joinedload(Room.property).selectinload(Property.ownerships).joinedload(PropertyOwnership.rent_bank_account),
                selectinload(Booking.parties),
                selectinload(Booking.sepa_mandate_links).joinedload(BookingSepaMandate.mandate).joinedload(SepaMandate.creditor_profile),
            )
            .where(Booking.id == booking_id)
        )

    def active_binding(self, db: Session, booking_id: int) -> BookingSepaMandate | None:
        return db.scalar(select(BookingSepaMandate).where(BookingSepaMandate.booking_id == booking_id, BookingSepaMandate.active.is_(True)))

    def binding(self, db: Session, booking_id: int, mandate_id: int) -> BookingSepaMandate | None:
        return db.scalar(select(BookingSepaMandate).where(BookingSepaMandate.booking_id == booking_id, BookingSepaMandate.mandate_id == mandate_id))

    def compatible_profiles(self, db: Session, booking: Booking) -> list[SepaCreditorProfile]:
        account_ids = {
            item.rent_bank_account_id for item in booking.room.property.ownerships
            if item.active and item.rent_bank_account_id is not None
        }
        if not account_ids:
            return []
        return list(db.scalars(
            select(SepaCreditorProfile)
            .options(joinedload(SepaCreditorProfile.bank_account))
            .where(SepaCreditorProfile.active.is_(True), SepaCreditorProfile.bank_account_id.in_(account_ids))
            .order_by(SepaCreditorProfile.display_name, SepaCreditorProfile.id)
        ).unique())

    def compatible_mandates(self, db: Session, booking: Booking) -> list[SepaMandate]:
        profiles = self.compatible_profiles(db, booking)
        ids = [item.id for item in profiles]
        if not ids:
            return []
        return list(db.scalars(
            select(SepaMandate)
            .options(joinedload(SepaMandate.creditor_profile), joinedload(SepaMandate.person))
            .where(SepaMandate.creditor_profile_id.in_(ids), SepaMandate.status == "active")
            .order_by(SepaMandate.debtor_name, SepaMandate.id)
        ).unique())
