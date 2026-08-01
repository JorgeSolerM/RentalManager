from sqlalchemy.orm import Session

from backend.models.property import Property
from backend.repositories.property_repository import PropertyRepository


class PropertyService:

    def __init__(self):

        self.repository = PropertyRepository()

    def get_all(self, db: Session) -> list[Property]:

        return self.repository.get_all(db)
