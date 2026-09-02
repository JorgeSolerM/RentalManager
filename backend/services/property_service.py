from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.models.property import Property
from backend.repositories.property_repository import PropertyRepository
from backend.services.room_service import RoomService
from backend.core.property_address import (
    format_property_address,
    normalize_address_part,
)


class PropertyService:
    def __init__(self):
        self.repository = PropertyRepository()
        self.room_service = RoomService()

    def list_properties(self, db: Session) -> list[Property]:
        return self.repository.get_all(db)

    def get_by_id(self, db: Session, property_id: int) -> Property | None:
        return self.repository.get_by_id(db, property_id)

    def create_property(self, db: Session, property_obj: Property) -> OperationResult[Property]:
        property_obj.street = normalize_address_part(property_obj.street)
        property_obj.street_number = normalize_address_part(property_obj.street_number)
        property_obj.floor = normalize_address_part(property_obj.floor)
        property_obj.door = normalize_address_part(property_obj.door)
        property_obj.city = normalize_address_part(property_obj.city) or ""
        if not property_obj.street:
            return OperationResult(success=False, message="property_street_required")
        if not property_obj.city:
            return OperationResult(success=False, message="property_city_required")
        property_obj.address = format_property_address(property_obj)
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
        street: str, street_number: str | None, floor: str | None,
        door: str | None, city: str, notes: str | None,
    ) -> OperationResult[Property]:
        property_obj = self.repository.get_by_id(db, property_id)
        if property_obj is None:
            return OperationResult(success=False, message="not_found")
        existing = self.repository.get_by_name(db, name)
        if existing is not None and existing.id != property_obj.id:
            return OperationResult(success=False, message="name_exists")
        normalized_street = normalize_address_part(street)
        normalized_city = normalize_address_part(city)
        if not normalized_street:
            return OperationResult(success=False, message="property_street_required")
        if not normalized_city:
            return OperationResult(success=False, message="property_city_required")
        try:
            property_obj.name = name
            property_obj.alias = alias
            property_obj.street = normalized_street
            property_obj.street_number = normalize_address_part(street_number)
            property_obj.floor = normalize_address_part(floor)
            property_obj.door = normalize_address_part(door)
            property_obj.city = normalized_city
            property_obj.address = format_property_address(property_obj)
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
