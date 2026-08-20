import re
from sqlalchemy.orm import Session

from backend.core.operation_result import OperationResult
from backend.models.feature import Feature
from backend.repositories.feature_repository import FeatureRepository


SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class FeatureService:
    def __init__(self):
        self.repository = FeatureRepository()

    def list_all(self, db): return self.repository.list_all(db)

    def save(self, db: Session, feature_id: int | None, *, name: str, slug: str, scope: str, category: str, icon_key: str | None, display_order: int, active: bool):
        slug = slug.strip()
        if not SLUG.fullmatch(slug) or scope not in {"property", "room", "both"} or display_order < 0 or not name.strip() or not category.strip():
            return OperationResult(False, "feature_invalid")
        feature = self.repository.get(db, feature_id) if feature_id else None
        if feature_id and feature is None: return OperationResult(False, "not_found")
        duplicate = self.repository.by_slug(db, slug)
        if duplicate and duplicate.id != feature_id: return OperationResult(False, "feature_slug_exists")
        try:
            if feature is None:
                feature = Feature(); db.add(feature)
            feature.name = name.strip(); feature.slug = slug; feature.scope = scope
            feature.category = category.strip(); feature.icon_key = icon_key.strip() if icon_key and icon_key.strip() else None
            feature.display_order = display_order; feature.active = active
            db.flush(); db.commit()
            return OperationResult(True, data=feature)
        except Exception:
            db.rollback(); raise

    def delete(self, db: Session, feature_id: int):
        feature = self.repository.get(db, feature_id)
        if feature is None: return OperationResult(False, "not_found")
        if self.repository.in_use(db, feature_id): return OperationResult(False, "feature_in_use")
        try:
            db.delete(feature); db.flush(); db.commit(); return OperationResult(True)
        except Exception:
            db.rollback(); raise

