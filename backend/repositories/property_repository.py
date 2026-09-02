from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models.property import Property
from backend.models.property_ownership import PropertyOwnership
from backend.repositories.base_repository import BaseRepository


class PropertyRepository(BaseRepository):

    def get_all(self, db: Session) -> list[Property]:

        statement = select(Property).options(
            selectinload(Property.ownerships).selectinload(PropertyOwnership.owner),
            selectinload(Property.ownerships).selectinload(PropertyOwnership.rent_bank_account),
        ).order_by(Property.name)

        return db.scalars(statement).all()

    def get_by_id(
        self,
        db: Session,
        property_id: int,
    ) -> Property | None:

        statement = (
            select(Property).options(
                selectinload(Property.ownerships).selectinload(PropertyOwnership.owner),
                selectinload(Property.ownerships).selectinload(PropertyOwnership.rent_bank_account),
            )
            .where(Property.id == property_id)
        )

        return db.scalar(statement)

    def get_by_name(
        self,
        db: Session,
        name: str,
    ) -> Property | None:

        statement = (
            select(Property)
            .where(Property.name == name)
        )

        return db.scalar(statement)

