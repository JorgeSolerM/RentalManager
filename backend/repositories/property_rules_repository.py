from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models.property import Property
from backend.models.rental_requirement import RentalRequirement


class PropertyRulesRepository:
    def get_property(self, db: Session, property_id: int) -> Property | None:
        return db.scalar(
            select(Property)
            .options(selectinload(Property.requirements))
            .where(Property.id == property_id)
        )

    def requirement_options(
        self, db: Session, assigned_ids: set[int]
    ) -> list[RentalRequirement]:
        statement = select(RentalRequirement).where(
            RentalRequirement.active.is_(True)
            | RentalRequirement.id.in_(assigned_ids)
        ).order_by(
            RentalRequirement.display_order,
            RentalRequirement.public_name,
        )
        return list(db.scalars(statement).all())

    def selected_requirements(
        self, db: Session, requirement_ids: set[int]
    ) -> list[RentalRequirement]:
        if not requirement_ids:
            return []
        return list(
            db.scalars(
                select(RentalRequirement).where(
                    RentalRequirement.id.in_(requirement_ids)
                )
            ).all()
        )
