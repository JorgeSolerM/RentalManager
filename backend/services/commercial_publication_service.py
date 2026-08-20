from decimal import Decimal, InvalidOperation
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.core.operation_result import OperationResult
from backend.models.feature import Feature
from backend.models.property import Property
from backend.models.room import Room
from backend.services.publication_service import PUBLIC_SLUG_PATTERN, PublicationService


REASON_MESSAGES = {
    "property_inactive": "El inmueble está inactivo.", "property_not_published": "El inmueble no está publicado.",
    "property_public_title_required": "Falta el título público del inmueble.", "property_public_location_required": "Falta la ubicación pública del inmueble.",
    "property_public_slug_required": "Falta un slug válido para el inmueble.", "room_inactive": "La habitación está inactiva.",
    "room_not_published": "La habitación no está marcada como publicada.", "room_public_title_required": "Falta el título público.",
    "room_public_description_required": "Falta la descripción pública.", "room_public_slug_required": "Falta un slug válido.",
    "room_price_invalid": "El precio mensual no es válido.", "public_photo_required": "Falta una fotografía principal efectiva.",
}


class CommercialPublicationService:
    def __init__(self): self.publication = PublicationService()

    def feature_options(self, db: Session, target) -> list[Feature]:
        scope = "property" if isinstance(target, Property) else "room"
        current = {f.id for f in target.features}
        return list(db.scalars(select(Feature).where(
            ((Feature.scope == scope) | (Feature.scope == "both")),
            ((Feature.active.is_(True)) | (Feature.id.in_(current))),
        ).order_by(Feature.category, Feature.display_order, Feature.name)).all())

    def property_reasons(self, property_obj: Property, *, include_publish_flag=True):
        reasons = []
        if not property_obj.active: reasons.append("property_inactive")
        if include_publish_flag and not property_obj.is_published: reasons.append("property_not_published")
        if not property_obj.public_title or not property_obj.public_title.strip(): reasons.append("property_public_title_required")
        if not property_obj.public_location or not property_obj.public_location.strip(): reasons.append("property_public_location_required")
        if not property_obj.public_slug or not PUBLIC_SLUG_PATTERN.fullmatch(property_obj.public_slug): reasons.append("property_public_slug_required")
        return reasons

    def update_property(self, db: Session, property_id: int, *, title, location, slug, is_published, feature_ids):
        obj = db.scalar(select(Property).options(selectinload(Property.features)).where(Property.id == property_id))
        if obj is None: return OperationResult(False, "not_found")
        return self._update(db, obj, "property", title, None, location, slug, is_published, feature_ids)

    @staticmethod
    def _room_slug_suffix(code: str) -> str:
        trailing_digits = re.search(r"(\d+)$", code.strip())
        if trailing_digits:
            return f"h{trailing_digits.group(1)}"
        normalized = re.sub(r"[^a-z0-9]+", "-", code.strip().lower()).strip("-")
        return normalized

    def room_slug_preview(self, db: Session, room: Room) -> str | None:
        if room.public_slug:
            return room.public_slug
        property_slug = room.property.public_slug if room.property else None
        if not property_slug or not PUBLIC_SLUG_PATTERN.fullmatch(property_slug):
            return None
        suffix = self._room_slug_suffix(room.code)
        if not suffix:
            return None
        candidate = f"{property_slug}-{suffix}"
        existing = db.scalar(select(Room.id).where(Room.public_slug == candidate, Room.id != room.id))
        return f"{candidate}-{room.id}" if existing is not None else candidate

    @staticmethod
    def _optional_decimal(value, *, allow_zero: bool) -> Decimal | None:
        if value is None or not str(value).strip():
            return None
        try:
            parsed = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            raise ValueError
        if not parsed.is_finite() or parsed < 0 or (not allow_zero and parsed == 0):
            raise ValueError
        return parsed

    def update_room(self, db: Session, room_id: int, *, title, description, base_price, square_meters, is_published, feature_ids):
        obj = db.scalar(select(Room).options(selectinload(Room.features), selectinload(Room.property)).where(Room.id == room_id))
        if obj is None: return OperationResult(False, "not_found")
        try:
            parsed_price = self._optional_decimal(base_price, allow_zero=True)
            parsed_square_meters = self._optional_decimal(square_meters, allow_zero=True)
        except ValueError:
            return OperationResult(False, "room_commercial_values_invalid")
        slug = obj.public_slug or self.room_slug_preview(db, obj)
        return self._update(db, obj, "room", title, description, None, slug, is_published, feature_ids, base_price=parsed_price, square_meters=parsed_square_meters)

    def _update(self, db, obj, scope, title, description, location, slug, is_published, feature_ids, *, base_price=None, square_meters=None):
        slug = slug.strip() if slug else None
        if slug and not PUBLIC_SLUG_PATTERN.fullmatch(slug): return OperationResult(False, "public_slug_invalid")
        model = Property if scope == "property" else Room
        duplicate = db.scalar(select(model).where(model.public_slug == slug, model.id != obj.id)) if slug else None
        if duplicate: return OperationResult(False, "public_slug_exists")
        current_inactive = [f for f in obj.features if not f.active]
        selected = list(db.scalars(select(Feature).where(Feature.id.in_(set(feature_ids)))).all()) if feature_ids else []
        if any(not f.active and f.id not in {x.id for x in current_inactive} for f in selected): return OperationResult(False, "feature_inactive")
        if any(f.scope not in {scope, "both"} for f in selected): return OperationResult(False, "feature_wrong_scope")
        selected_ids = {f.id for f in selected}; selected.extend(f for f in current_inactive if f.id not in selected_ids)
        try:
            obj.public_title = title.strip() if title else None
            if scope == "property":
                obj.public_location = location.strip() if location else None
            else:
                obj.public_description = description.strip() if description else None
                obj.base_price = base_price
                obj.square_meters = square_meters
            obj.public_slug = slug; obj.features = selected; obj.is_published = False
            db.flush()
            if is_published:
                reasons = self.property_reasons(obj, include_publish_flag=False) if scope == "property" else [r for r in self.publication.assess_room(db, obj.id).reasons if r != "room_not_published"]
                if reasons:
                    # Preserve the valid draft while refusing the publish flag.
                    db.commit(); return OperationResult(False, "publication_requirements", reasons)
                obj.is_published = True; db.flush()
            db.commit(); return OperationResult(True, data=obj)
        except Exception:
            db.rollback(); raise
