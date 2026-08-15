from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.models.property import Property
from backend.repositories.property_repository import PropertyRepository
from backend.services.room_service import RoomService


class PropertyService:
    def __init__(self):
        self.repository = PropertyRepository()
        self.room_service = RoomService()

    def list_properties(self, db: Session) -> list[Property]:
        return self.repository.get_all(db)

    def get_by_id(self, db: Session, property_id: int) -> Property | None:
        return self.repository.get_by_id(db, property_id)

    def create_property(self, db: Session, property_obj: Property) -> OperationResult[Property]:
        if self.repository.get_by_name(db, property_obj.name) is not None:
            return OperationResult(success=False, message="name_exists")
        try:
            self.repository.create(db, property_obj)
            db.commit()
            return OperationResult(success=True, data=property_obj)
        except Exception:
            db.rollback()
            raise

    def update_property(
        self, db: Session, property_id: int, name: str, alias: str | None,
        address: str, city: str, owner: str, notes: str | None,
    ) -> OperationResult[Property]:
        property_obj = self.repository.get_by_id(db, property_id)
        if property_obj is None:
            return OperationResult(success=False, message="not_found")
        existing = self.repository.get_by_name(db, name)
        if existing is not None and existing.id != property_obj.id:
            return OperationResult(success=False, message="name_exists")
        try:
            property_obj.name = name
            property_obj.alias = alias
            property_obj.address = address
            property_obj.city = city
            property_obj.owner = owner
            property_obj.notes = notes
            self.repository.update(db, property_obj)
            db.commit()
            return OperationResult(success=True, data=property_obj)
        except Exception:
            db.rollback()
            raise

    def toggle_property(self, db: Session, property_id: int) -> OperationResult[Property]:
        property_obj = self.repository.get_by_id(db, property_id)
        if property_obj is None:
            return OperationResult(success=False, message="not_found")
        try:
            property_obj.active = not property_obj.active
            self.repository.update(db, property_obj)
            db.commit()
            return OperationResult(success=True, data=property_obj)
        except Exception:
            db.rollback()
            raise

    def delete_property(self, db: Session, property_id: int) -> OperationResult[None]:
        property_obj = self.repository.get_by_id(db, property_id)
        if property_obj is None:
            return OperationResult(success=False, message="not_found")
        if self.room_service.count_rooms_by_property(db, property_obj.id) > 0:
            return OperationResult(success=False, message="property_has_rooms")
        try:
            self.repository.delete(db, property_obj)
            db.commit()
            return OperationResult(success=True)
        except Exception:
            db.rollback()
            raise
