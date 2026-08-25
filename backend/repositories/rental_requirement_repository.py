from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.rental_requirement import RentalRequirement, property_requirements


class RentalRequirementRepository:
    def list_all(self, db: Session) -> list[RentalRequirement]:
        return list(
            db.scalars(
                select(RentalRequirement).order_by(
                    RentalRequirement.display_order,
                    RentalRequirement.public_name,
                )
            ).all()
        )

    def get(self, db: Session, requirement_id: int) -> RentalRequirement | None:
        return db.get(RentalRequirement, requirement_id)

    def by_slug(self, db: Session, slug: str) -> RentalRequirement | None:
        return db.scalar(
            select(RentalRequirement).where(RentalRequirement.slug == slug)
        )

    def in_use(self, db: Session, requirement_id: int) -> bool:
        count = db.scalar(
            select(func.count())
            .select_from(property_requirements)
            .where(property_requirements.c.requirement_id == requirement_id)
        )
        return bool(count)
