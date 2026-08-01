from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.property import Property


class PropertyRepository:

    def get_all(self, db: Session) -> list[Property]:

        statement = select(Property).order_by(Property.name)

        return db.scalars(statement).all()
