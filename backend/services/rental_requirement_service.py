import re

from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.models.rental_requirement import RentalRequirement
from backend.repositories.rental_requirement_repository import (
    RentalRequirementRepository,
)


SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class RentalRequirementService:
    def __init__(self):
        self.repository = RentalRequirementRepository()

    def list_all(self, db: Session) -> list[RentalRequirement]:
        return self.repository.list_all(db)

    def save(
        self,
        db: Session,
        requirement_id: int | None,
        *,
        public_name: str,
        slug: str,
        public_description: str | None,
        display_order: int,
        active: bool,
    ) -> OperationResult:
        name = public_name.strip()
        stable_slug = slug.strip()
        if (
            not name
            or not SLUG_PATTERN.fullmatch(stable_slug)
            or display_order < 0
        ):
            return OperationResult(False, "requirement_invalid")
        requirement = (
            self.repository.get(db, requirement_id) if requirement_id else None
        )
        if requirement_id and requirement is None:
            return OperationResult(False, "not_found")
        duplicate = self.repository.by_slug(db, stable_slug)
        if duplicate and duplicate.id != requirement_id:
            return OperationResult(False, "requirement_slug_exists")
        try:
            if requirement is None:
                requirement = RentalRequirement()
                db.add(requirement)
            requirement.public_name = name
            requirement.slug = stable_slug
            requirement.public_description = (
                public_description.strip()
                if public_description and public_description.strip()
                else None
            )
            requirement.display_order = display_order
            requirement.active = active
            db.flush()
            db.commit()
            return OperationResult(True, data=requirement)
        except Exception:
            db.rollback()
            raise

    def delete(self, db: Session, requirement_id: int) -> OperationResult:
        requirement = self.repository.get(db, requirement_id)
        if requirement is None:
            return OperationResult(False, "not_found")
        if self.repository.in_use(db, requirement_id):
            return OperationResult(False, "requirement_in_use")
        try:
            db.delete(requirement)
            db.flush()
            db.commit()
            return OperationResult(True)
        except Exception:
            db.rollback()
            raise
