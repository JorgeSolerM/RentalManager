from sqlalchemy.orm import Session

from backend.models.room import Room
from backend.repositories.room_repository import RoomRepository


class RoomService:

    def __init__(self):

        self.room_repository = RoomRepository()

    def list_rooms(
        self,
        db: Session,
    ) -> list[Room]:

        return self.room_repository.get_all(db)

    def list_rooms_by_property(
        self,
        db: Session,
        property_id: int,
    ) -> list[Room]:

        return self.room_repository.get_by_property(
            db,
            property_id,
        )

    def count_rooms_by_property(
        self,
        db: Session,
        property_id: int,
    ) -> int:

        return self.room_repository.count_by_property(
            db,
            property_id,
        )

    def get_room(
        self,
        db: Session,
        room_id: int,
    ) -> Room | None:

        return self.room_repository.get_by_id(
            db,
            room_id,
        )

    def create_room(
        self,
        db: Session,
        room: Room,
    ) -> Room:

        return self.room_repository.create(
            db,
            room,
        )

    def update_room(
        self,
        db: Session,
        room: Room,
    ) -> Room:

        return self.room_repository.update(
            db,
            room,
        )
