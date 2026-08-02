from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.property import Property


class PropertyRepository:

    def get_all(self, db: Session) -> list[Property]:

        statement = select(Property).order_by(Property.name)

        return db.scalars(statement).all()

    def create(self, db: Session, property_obj: Property) -> Property:

        db.add(property_obj)
        db.commit()
        db.refresh(property_obj)

        return property_obj
