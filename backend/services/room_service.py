from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.models.room import Room
from backend.repositories.room_repository import RoomRepository


class RoomService:

    def __init__(self):

        self.repository = RoomRepository()

    def list_rooms(
        self,
        db: Session,
    ) -> list[Room]:

        return self.repository.get_all(db)

    def list_rooms_by_property(
        self,
        db: Session,
        property_id: int,
    ) -> list[Room]:

        return self.repository.get_by_property(
            db,
            property_id,
        )

    def count_rooms_by_property(
        self,
        db: Session,
        property_id: int,
    ) -> int:

        return self.repository.count_by_property(
            db,
            property_id,
        )

    def get_room(
        self,
        db: Session,
        room_id: int,
    ) -> Room | None:

        return self.repository.get_by_id(
            db,
            room_id,
        )

    def create_room(
        self,
        db: Session,
        room: Room,
    ) -> OperationResult:

        existing = self.repository.get_by_code(
            db,
            room.code,
        )

        if existing is not None:

            return OperationResult(
                success=False,
                message="code_exists",
            )

        self.repository.create(
            db,
            room,
        )

        db.commit()

        db.refresh(room)

        return OperationResult(
            success=True,
            data=room,
        )

    def update_room(
        self,
        db: Session,
        room: Room,
    ) -> OperationResult:

        existing = self.repository.get_by_code(
            db,
            room.code,
        )

        if (
            existing is not None
            and existing.id != room.id
        ):

            return OperationResult(
                success=False,
                message="code_exists",
            )

        self.repository.update(
            db,
            room,
        )

        db.commit()

        db.refresh(room)

        return OperationResult(
            success=True,
            data=room,
        )

    def delete_room(
        self,
        db: Session,
        room: Room,
    ) -> OperationResult:

        self.repository.delete(
            db,
            room,
        )

        db.commit()

        return OperationResult(
            success=True,
        )
