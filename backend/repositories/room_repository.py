from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.room import Room


class RoomRepository:

    def get_all(
        self,
        db: Session,
    ) -> list[Room]:

        statement = (
            select(Room)
            .order_by(
                Room.property_id,
                Room.display_order,
            )
        )

        return db.scalars(statement).all()

    def get_by_property(
        self,
        db: Session,
        property_id: int,
    ) -> list[Room]:

        statement = (
            select(Room)
            .where(Room.property_id == property_id)
            .order_by(Room.display_order)
        )

        return db.scalars(statement).all()

    def count_by_property(
        self,
        db: Session,
        property_id: int,
    ) -> int:

        statement = (
            select(func.count())
            .select_from(Room)
            .where(Room.property_id == property_id)
        )

        return db.scalar(statement) or 0

    def get_by_id(
        self,
        db: Session,
        room_id: int,
    ) -> Room | None:

        statement = (
            select(Room)
            .where(Room.id == room_id)
        )

        return db.scalar(statement)

    def create(
        self,
        db: Session,
        room: Room,
    ) -> Room:

        db.add(room)

        db.commit()

        db.refresh(room)

        return room

    def update(
        self,
        db: Session,
        room: Room,
    ) -> Room:

        db.commit()

        db.refresh(room)

        return room
