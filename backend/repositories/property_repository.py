from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.property import Property


class PropertyRepository:

    def get_all(self, db: Session) -> list[Property]:

        statement = select(Property).order_by(Property.name)

        return db.scalars(statement).all()

    def get_by_id(
        self,
        db: Session,
        property_id: int,
    ) -> Property | None:

        statement = (
            select(Property)
            .where(Property.id == property_id)
        )

        return db.scalar(statement)

    def create(
        self,
        db: Session,
        property_obj: Property,
    ) -> Property:

        db.add(property_obj)

        db.commit()

        db.refresh(property_obj)

        return property_obj

    def update(
        self,
        db: Session,
        property_obj: Property,
    ) -> Property:

        db.commit()

        db.refresh(property_obj)

        return property_obj
