from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.repositories.property_rules_repository import PropertyRulesRepository


TRISTATE_VALUES = {"unknown": None, "yes": True, "no": False}


class PropertyRulesService:
    def __init__(self):
        self.repository = PropertyRulesRepository()

    def get(self, db: Session, property_id: int):
        return self.repository.get_property(db, property_id)

    def requirement_options(self, db: Session, property_obj):
        assigned = {item.id for item in property_obj.requirements}
        return self.repository.requirement_options(db, assigned)

    @staticmethod
    def _age(value: str | int | None) -> int | None:
        if value is None or not str(value).strip():
            return None
        parsed = int(value)
        if parsed < 0:
            raise ValueError
        return parsed

    def update(
        self,
        db: Session,
        property_id: int,
        *,
        smoking_allowed: str,
        pets_allowed: str,
        musical_instruments_allowed: str,
        minimum_tenant_age: str | int | None,
        maximum_tenant_age: str | int | None,
        requirement_ids: list[int],
    ) -> OperationResult:
        policies = (
            smoking_allowed,
            pets_allowed,
            musical_instruments_allowed,
        )
        if any(value not in TRISTATE_VALUES for value in policies):
            return OperationResult(False, "property_rules_invalid")
        try:
            minimum = self._age(minimum_tenant_age)
            maximum = self._age(maximum_tenant_age)
        except (TypeError, ValueError):
            return OperationResult(False, "property_age_invalid")
        if minimum is not None and maximum is not None and minimum > maximum:
            return OperationResult(False, "property_age_range_invalid")

        property_obj = self.repository.get_property(db, property_id)
        if property_obj is None:
            return OperationResult(False, "not_found")
        unique_ids = set(requirement_ids)
        selected = self.repository.selected_requirements(db, unique_ids)
        if len(selected) != len(unique_ids):
            return OperationResult(False, "requirement_invalid")
        current_ids = {item.id for item in property_obj.requirements}
        if any(not item.active and item.id not in current_ids for item in selected):
            return OperationResult(False, "requirement_inactive")

        try:
            (
                property_obj.smoking_allowed,
                property_obj.pets_allowed,
                property_obj.musical_instruments_allowed,
            ) = tuple(TRISTATE_VALUES[value] for value in policies)
            property_obj.minimum_tenant_age = minimum
            property_obj.maximum_tenant_age = maximum
            property_obj.requirements = selected
            db.flush()
            db.commit()
            return OperationResult(True, data=property_obj)
        except Exception:
            db.rollback()
            raise
