from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.models.room import Room
from backend.repositories.room_repository import RoomRepository


class RoomService:
    def __init__(self):
        self.repository = RoomRepository()

    def list_rooms(self, db: Session) -> list[Room]:
        return self.repository.get_all(db)

    def list_rooms_by_property(self, db: Session, property_id: int) -> list[Room]:
        return self.repository.get_by_property(db, property_id)

    def count_rooms_by_property(self, db: Session, property_id: int) -> int:
        return self.repository.count_by_property(db, property_id)

    def get_room(self, db: Session, room_id: int) -> Room | None:
        return self.repository.get_by_id(db, room_id)

    def create_room(self, db: Session, room: Room) -> OperationResult[Room]:
        if self.repository.get_by_code(db, room.code) is not None:
            return OperationResult(success=False, message="code_exists")
        try:
            self.repository.create(db, room)
            db.commit()
            return OperationResult(success=True, data=room)
        except Exception:
            db.rollback()
            raise

    def update_room(
        self, db: Session, room_id: int, code: str, base_price: float,
        square_meters: float | None,
    ) -> OperationResult[Room]:
        room = self.repository.get_by_id(db, room_id)
        if room is None:
            return OperationResult(success=False, message="not_found")
        existing = self.repository.get_by_code(db, code)
        if existing is not None and existing.id != room.id:
            return OperationResult(success=False, message="code_exists")
        try:
            room.code = code
            room.base_price = base_price
            room.square_meters = square_meters
            self.repository.update(db, room)
            db.commit()
            return OperationResult(success=True, data=room)
        except Exception:
            db.rollback()
            raise

    def delete_room(self, db: Session, room_id: int) -> OperationResult[None]:
        room = self.repository.get_by_id(db, room_id)
        if room is None:
            return OperationResult(success=False, message="not_found")
        if self.repository.has_bookings(db, room.id):
            return OperationResult(success=False, message="room_has_bookings")
        if self.repository.has_room_calendars(db, room.id):
            return OperationResult(success=False, message="room_has_room_calendars")
        try:
            self.repository.delete(db, room)
            db.commit()
            return OperationResult(success=True)
        except Exception:
            db.rollback()
            raise
