from decimal import Decimal, InvalidOperation
import re

from sqlalchemy import case, select
from sqlalchemy.orm import Session, selectinload

from backend.core.operation_result import OperationResult
from backend.models.feature import Feature
from backend.models.property import Property
from backend.models.room import Room
from backend.models.manager import Manager
from backend.models.room_public_highlight import RoomPublicHighlight
from backend.services.publication_service import PUBLIC_SLUG_PATTERN, PublicationService


REASON_MESSAGES = {
    "property_inactive": "El inmueble está inactivo.", "property_not_published": "El inmueble no está publicado.",
    "property_public_title_required": "Falta el título público del inmueble.", "property_public_location_required": "Falta la ubicación pública del inmueble.",
    "property_public_slug_required": "Falta un slug válido para el inmueble.", "room_inactive": "La habitación está inactiva.",
    "room_not_published": "La habitación no está marcada como publicada.", "room_public_title_required": "Falta el título público.",
    "room_public_description_required": "Falta la descripción pública.", "room_public_slug_required": "Falta un slug válido.",
    "room_price_invalid": "El precio mensual no es válido.", "public_photo_required": "Falta una fotografía principal efectiva.",
    "property_manager_required": "Falta un gestor activo para el inmueble.",
    "highlight_invalid": "Solo puedes destacar hasta cuatro características efectivas de la habitación.",
    "room_minimum_stay_required": "Falta definir la estancia mínima.",
    "room_minimum_stay_negative": "La estancia mínima no puede ser negativa.",
    "room_maximum_stay_invalid": "La estancia máxima debe ser mayor que cero.",
    "room_stay_range_invalid": "La estancia máxima no puede ser menor que la mínima.",
    "room_bed_capacity_required": "Debe seleccionarse exactamente un tipo de cama: individual o doble.",
    "room_tenant_gender_invalid": "La preferencia de inquilino no es válida.",
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

    @staticmethod
    def highlight_options(room: Room) -> list[Feature]:
        current = {highlight.feature_id for highlight in room.public_highlights}
        features = {feature.id: feature for feature in (*room.features, *room.property.features)}
        return sorted(
            (feature for feature in features.values() if feature.active or feature.id in current),
            key=lambda feature: (feature.category, feature.display_order, feature.name),
        )

    @staticmethod
    def copy_source_options(db: Session, destination: Room) -> list[Room]:
        return list(db.scalars(
            select(Room)
            .join(Room.property)
            .options(selectinload(Room.property))
            .where(Room.id != destination.id)
            .order_by(
                case((Room.property_id == destination.property_id, 0), else_=1),
                Property.name,
                Room.display_order,
                Room.code,
            )
        ).all())

    @staticmethod
    def _available_copied_title(db: Session, destination: Room, source_title: str | None):
        if not source_title or not source_title.strip():
            return None
        base = source_title.strip()
        existing = set(db.scalars(
            select(Room.public_title).where(
                Room.property_id == destination.property_id,
                Room.id != destination.id,
                Room.public_title.is_not(None),
            )
        ).all())
        if base not in existing:
            return base
        suffix = 2
        while f"{base} ({suffix})" in existing:
            suffix += 1
        return f"{base} ({suffix})"

    def copy_room_configuration(self, db: Session, destination_id: int, source_id: int):
        options = (
            selectinload(Room.features),
            selectinload(Room.public_highlights).selectinload(RoomPublicHighlight.feature),
            selectinload(Room.property).selectinload(Property.features),
        )
        destination = db.scalar(select(Room).options(*options).where(Room.id == destination_id))
        source = db.scalar(select(Room).options(*options).where(Room.id == source_id))
        if destination is None or source is None:
            return OperationResult(False, "not_found")
        if destination.id == source.id:
            return OperationResult(False, "room_feature_copy_same_room")

        copied_features = [
            feature for feature in source.features
            if feature.active and feature.scope in {"room", "both"}
        ]
        inactive_omitted = len(source.features) - len(copied_features)
        effective_ids = {
            feature.id for feature in copied_features
        } | {
            feature.id for feature in destination.property.features if feature.active
        }
        copied_highlight_ids = [
            highlight.feature_id for highlight in source.public_highlights
            if highlight.feature.active and highlight.feature_id in effective_ids
        ][:4]
        highlights_omitted = len(source.public_highlights) - len(copied_highlight_ids)
        copied_title = self._available_copied_title(db, destination, source.public_title)

        try:
            had_highlights = bool(destination.public_highlights)
            destination.public_highlights.clear()
            if had_highlights:
                db.flush()
            destination.features = copied_features
            destination.public_title = copied_title
            destination.public_description = source.public_description
            destination.minimum_stay_months = source.minimum_stay_months
            destination.maximum_stay_months = source.maximum_stay_months
            destination.tenant_gender_preference = source.tenant_gender_preference
            destination.public_highlights = [
                RoomPublicHighlight(feature_id=feature_id, position=position)
                for position, feature_id in enumerate(copied_highlight_ids)
            ]
            db.flush()
            db.commit()
            return OperationResult(True, data={
                "source_code": source.code,
                "inactive_features_omitted": inactive_omitted,
                "highlights_omitted": highlights_omitted,
            })
        except Exception:
            db.rollback()
            raise

    def property_reasons(self, property_obj: Property, *, include_publish_flag=True):
        reasons = []
        if not property_obj.active: reasons.append("property_inactive")
        if include_publish_flag and not property_obj.is_published: reasons.append("property_not_published")
        if not property_obj.public_title or not property_obj.public_title.strip(): reasons.append("property_public_title_required")
        if not property_obj.public_location or not property_obj.public_location.strip(): reasons.append("property_public_location_required")
        if not property_obj.public_slug or not PUBLIC_SLUG_PATTERN.fullmatch(property_obj.public_slug): reasons.append("property_public_slug_required")
        if property_obj.manager is None or not property_obj.manager.active: reasons.append("property_manager_required")
        return reasons

    def update_property(self, db: Session, property_id: int, *, title, location, slug, is_published, feature_ids, manager_id=None, shared_full_bathroom_count=None, shared_toilet_count=None):
        obj = db.scalar(select(Property).options(
            selectinload(Property.features),
            selectinload(Property.manager),
            selectinload(Property.rooms).selectinload(Room.features),
            selectinload(Property.rooms).selectinload(Room.public_highlights),
        ).where(Property.id == property_id))
        if obj is None: return OperationResult(False, "not_found")
        manager = db.get(Manager, manager_id) if manager_id else None
        if manager_id and (manager is None or not manager.active): return OperationResult(False, "manager_invalid")
        try:
            parsed_full_bathrooms = self._optional_integer(
                shared_full_bathroom_count, minimum=0
            )
            parsed_toilets = self._optional_integer(shared_toilet_count, minimum=0)
        except ValueError:
            return OperationResult(False, "property_shared_bathroom_counts_invalid")
        return self._update(
            db, obj, "property", title, None, location, slug, is_published,
            feature_ids, manager=manager,
            shared_full_bathroom_count=parsed_full_bathrooms,
            shared_toilet_count=parsed_toilets,
        )

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

    @staticmethod
    def _optional_integer(value, *, minimum: int) -> int | None:
        if value is None or not str(value).strip():
            return None
        text_value = str(value).strip()
        if not re.fullmatch(r"-?\d+", text_value):
            raise ValueError
        parsed = int(text_value)
        if parsed < minimum:
            raise ValueError
        return parsed

    def update_room(self, db: Session, room_id: int, *, title, description, base_price, square_meters, is_published, feature_ids, highlight_feature_ids=(), minimum_stay_months=None, maximum_stay_months=None, tenant_gender_preference="any"):
        obj = db.scalar(select(Room).options(
            selectinload(Room.features),
            selectinload(Room.public_highlights),
            selectinload(Room.property).selectinload(Property.features),
        ).where(Room.id == room_id))
        if obj is None: return OperationResult(False, "not_found")
        try:
            parsed_price = self._optional_decimal(base_price, allow_zero=False)
            parsed_square_meters = self._optional_decimal(square_meters, allow_zero=True)
        except ValueError:
            return OperationResult(False, "room_commercial_values_invalid")
        try:
            parsed_minimum_stay = self._optional_integer(minimum_stay_months, minimum=0)
            parsed_maximum_stay = self._optional_integer(maximum_stay_months, minimum=1)
        except ValueError:
            return OperationResult(False, "room_stay_conditions_invalid")
        if parsed_minimum_stay is not None and parsed_minimum_stay > 0 and parsed_maximum_stay is not None and parsed_maximum_stay < parsed_minimum_stay:
            return OperationResult(False, "room_stay_range_invalid")
        if tenant_gender_preference not in {"any", "male", "female"}:
            return OperationResult(False, "room_tenant_gender_invalid")
        highlight_ids = list(dict.fromkeys(highlight_feature_ids))
        effective_ids = {feature.id for feature in obj.features} | {feature.id for feature in obj.property.features}
        selected_room_ids = set(feature_ids)
        effective_ids = (effective_ids - {feature.id for feature in obj.features}) | selected_room_ids
        current_highlight_ids = {highlight.feature_id for highlight in obj.public_highlights}
        invalid_ids = {feature_id for feature_id in highlight_ids if feature_id not in effective_ids}
        removable_ids = invalid_ids & current_highlight_ids
        highlight_ids = [feature_id for feature_id in highlight_ids if feature_id not in removable_ids]
        if len(highlight_ids) > 4 or any(feature_id not in effective_ids for feature_id in highlight_ids):
            return OperationResult(False, "highlight_invalid")
        slug = obj.public_slug or self.room_slug_preview(db, obj)
        return self._update(db, obj, "room", title, description, None, slug, is_published, feature_ids, base_price=parsed_price, square_meters=parsed_square_meters, highlight_feature_ids=highlight_ids, minimum_stay_months=parsed_minimum_stay, maximum_stay_months=parsed_maximum_stay, tenant_gender_preference=tenant_gender_preference)

    def _update(self, db, obj, scope, title, description, location, slug, is_published, feature_ids, *, base_price=None, square_meters=None, highlight_feature_ids=(), manager=None, minimum_stay_months=None, maximum_stay_months=None, tenant_gender_preference=None, shared_full_bathroom_count=None, shared_toilet_count=None):
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
        if scope == "room":
            effective_ids = selected_ids | {feature.id for feature in obj.property.features}
            if any(feature_id not in effective_ids for feature_id in highlight_feature_ids):
                return OperationResult(False, "highlight_invalid")
        try:
            obj.public_title = title.strip() if title else None
            if scope == "property":
                obj.public_location = location.strip() if location else None
                obj.manager = manager
                obj.shared_full_bathroom_count = shared_full_bathroom_count
                obj.shared_toilet_count = shared_toilet_count
                effective_property_ids = {feature.id for feature in selected}
                for room in obj.rooms:
                    effective_room_ids = effective_property_ids | {feature.id for feature in room.features}
                    remaining_highlights = [
                        highlight
                        for highlight in room.public_highlights
                        if highlight.feature_id in effective_room_ids
                    ]
                    removed_highlights = [
                        highlight
                        for highlight in room.public_highlights
                        if highlight.feature_id not in effective_room_ids
                    ]
                    for highlight in removed_highlights:
                        db.delete(highlight)
                    if removed_highlights:
                        db.flush()
                    for position, highlight in enumerate(remaining_highlights):
                        highlight.position = position
                    room.public_highlights = remaining_highlights
            else:
                obj.public_description = description.strip() if description else None
                obj.base_price = base_price
                obj.square_meters = square_meters
                obj.minimum_stay_months = minimum_stay_months
                obj.maximum_stay_months = maximum_stay_months
                obj.tenant_gender_preference = tenant_gender_preference
                # Replacing the collection directly can make SQLAlchemy update
                # existing positions before deleting obsolete rows.  With the
                # unique (room_id, position) constraint that creates a transient
                # collision when an item is inserted or reordered.  Remove and
                # flush first, then rebuild consecutive positions atomically.
                for highlight in list(obj.public_highlights):
                    db.delete(highlight)
                if obj.public_highlights:
                    db.flush()
                obj.public_highlights = [
                    RoomPublicHighlight(feature_id=feature_id, position=position)
                    for position, feature_id in enumerate(highlight_feature_ids)
                ]
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
