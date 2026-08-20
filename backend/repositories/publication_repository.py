from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from backend.models.feature import Feature
from backend.models.booking import Booking
from backend.models.property import Property
from backend.models.property_photo import PropertyPhoto
from backend.models.room import Room
from backend.models.room_photo import RoomPhoto


class PublicationRepository:
    def get_room_candidate(self, db: Session, room_id: int) -> Room | None:
        statement = (
            select(Room)
            .options(
                joinedload(Room.property)
                .selectinload(Property.photos)
                .joinedload(PropertyPhoto.asset),
                selectinload(Room.photos).joinedload(RoomPhoto.asset),
            )
            .where(Room.id == room_id)
        )
        return db.scalar(statement)

    def list_features(
        self,
        db: Session,
        *,
        active_only: bool = True,
    ) -> list[Feature]:
        statement = select(Feature).order_by(
            Feature.category, Feature.display_order, Feature.name
        )
        if active_only:
            statement = statement.where(Feature.active.is_(True))
        return list(db.scalars(statement).all())

    def list_relevant_booking_intervals(self, db: Session, room_id: int, today):
        return list(
            db.execute(
                select(Booking.check_in, Booking.check_out)
                .where(Booking.room_id == room_id, Booking.check_out > today)
                .order_by(Booking.check_in, Booking.check_out)
            ).all()
        )
