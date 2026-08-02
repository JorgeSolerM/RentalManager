from sqlalchemy.orm import Session

from backend.models.property import Property
from backend.repositories.property_repository import PropertyRepository


class PropertyService:

    def __init__(self):

        self.property_repository = PropertyRepository()

    def list_properties(self, db: Session) -> list[Property]:

        return self.property_repository.get_all(db)

    def create_property(self, db: Session, property_obj: Property) -> Property:

        return self.property_repository.create(db, property_obj)
