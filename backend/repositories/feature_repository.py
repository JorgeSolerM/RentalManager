from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models.feature import Feature, property_features, room_features


class FeatureRepository:
    def list_all(self, db: Session) -> list[Feature]:
        return list(db.scalars(select(Feature).order_by(Feature.category, Feature.display_order, Feature.name)).all())

    def get(self, db: Session, feature_id: int) -> Feature | None:
        return db.get(Feature, feature_id)

    def by_slug(self, db: Session, slug: str) -> Feature | None:
        return db.scalar(select(Feature).where(Feature.slug == slug))

    def in_use(self, db: Session, feature_id: int) -> bool:
        p = db.scalar(select(func.count()).select_from(property_features).where(property_features.c.feature_id == feature_id)) or 0
        r = db.scalar(select(func.count()).select_from(room_features).where(room_features.c.feature_id == feature_id)) or 0
        return p + r > 0

