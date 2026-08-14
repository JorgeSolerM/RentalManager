from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.models.property import Property
from backend.repositories.property_repository import PropertyRepository
from backend.services.room_service import RoomService

class PropertyService:

    def __init__(self):

        self.repository = PropertyRepository()

        self.room_service = RoomService()

    def list_properties(
        self,
        db: Session,
    ) -> list[Property]:

        return self.repository.get_all(db)

    def get_by_id(
        self,
        db: Session,
        property_id: int,
    ) -> Property | None:

        return self.repository.get_by_id(
            db,
            property_id,
        )

    def create_property(
        self,
        db: Session,
        property_obj: Property,
    ) -> OperationResult:

        existing = self.repository.get_by_name(
            db,
            property_obj.name,
        )

        if existing is not None:

            return OperationResult(
                success=False,
                message="name_exists",
            )

        self.repository.create(
            db,
            property_obj,
        )

        db.commit()

        db.refresh(
            property_obj,
        )

        return OperationResult(
            success=True,
            data=property_obj,
        )

    def update_property(
        self,
        db: Session,
        property_obj: Property,
    ) -> OperationResult:

        existing = self.repository.get_by_name(
            db,
            property_obj.name,
        )

        if (
            existing is not None
            and existing.id != property_obj.id
        ):

            return OperationResult(
                success=False,
                message="name_exists",
            )

        self.repository.update(
            db,
            property_obj,
        )

        db.commit()

        db.refresh(
            property_obj,
        )

        return OperationResult(
            success=True,
            data=property_obj,
        )

    def toggle_property(
        self,
        db: Session,
        property_obj: Property,
    ) -> Property:

        property_obj.active = (
            not property_obj.active
        )

        self.repository.update(
            db,
            property_obj,
        )

        db.commit()

        db.refresh(
            property_obj,
        )

        return property_obj

    def delete_property(
        self,
        db: Session,
        property_obj: Property,
    ) -> OperationResult:

        room_count = self.room_service.count_rooms_by_property(
            db,
            property_obj.id,
        )

        if room_count > 0:

            return OperationResult(
                success=False,
                message="property_has_rooms",
            )

        self.repository.delete(
            db,
            property_obj,
        )

        db.commit()

        return OperationResult(
            success=True,
        )
