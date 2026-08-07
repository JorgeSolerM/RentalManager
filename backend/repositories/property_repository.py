from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.property import Property
from backend.repositories.base_repository import BaseRepository


class PropertyRepository(BaseRepository):

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


