from decimal import Decimal
import re

from sqlalchemy.orm import Session

from backend.core.business_time import business_today
from backend.core.public_availability import first_commercial_gap
from backend.models.feature import Feature
from backend.repositories.publication_repository import PublicationRepository
from backend.schemas.publication_schema import (
    FeatureCatalogItem,
    EffectivePhoto,
    PublicAvailability,
    RoomPublicationAssessment,
)


PUBLIC_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
BED_CAPACITY_BY_SLUG = {"cama-individual": 1, "cama-doble": 2}


class PublicationService:
    def __init__(self, repository: PublicationRepository | None = None):
        self.repository = repository or PublicationRepository()

    @staticmethod
    def feature_can_apply_to(feature: Feature, target_scope: str) -> bool:
        if target_scope not in {"property", "room"}:
            return False
        return feature.scope in {target_scope, "both"}

    @staticmethod
    def _has_text(value: str | None) -> bool:
        return bool(value and value.strip())

    @staticmethod
    def _valid_slug(value: str | None) -> bool:
        return bool(value and PUBLIC_SLUG_PATTERN.fullmatch(value.strip()))

    @staticmethod
    def _price_is_valid(value) -> bool:
        if value is None:
            return False
        price = Decimal(value)
        return price.is_finite() and price > 0

    @staticmethod
    def room_capacity(room) -> int | None:
        capacities = [
            capacity
            for feature in room.features
            if feature.active
            for slug, capacity in BED_CAPACITY_BY_SLUG.items()
            if feature.slug == slug
        ]
        return capacities[0] if len(capacities) == 1 else None

    @staticmethod
    def _ready_primary(photos) -> bool:
        return any(
            photo.is_primary and photo.asset.status == "ready"
            for photo in photos
        )

    @staticmethod
    def _photo_dto(photo, source: str) -> EffectivePhoto:
        return EffectivePhoto(
            asset_id=photo.asset.id,
            source=source,
            position=photo.position,
            is_primary=photo.is_primary,
            width=photo.asset.width,
            height=photo.asset.height,
        )

    def _effective_primary_from_room(self, room) -> EffectivePhoto | None:
        room_primary = next(
            (photo for photo in room.photos if photo.is_primary and photo.asset.status == "ready"),
            None,
        )
        if room_primary is not None:
            return self._photo_dto(room_primary, "room")
        property_primary = next(
            (
                photo for photo in room.property.photos
                if photo.is_primary and photo.asset.status == "ready"
            ),
            None,
        )
        return self._photo_dto(property_primary, "property") if property_primary else None

    def get_effective_primary_photo(
        self, db: Session, room_id: int
    ) -> EffectivePhoto | None:
        room = self.repository.get_room_candidate(db, room_id)
        return self._effective_primary_from_room(room) if room is not None else None

    def get_effective_gallery(
        self, db: Session, room_id: int
    ) -> tuple[EffectivePhoto, ...]:
        room = self.repository.get_room_candidate(db, room_id)
        if room is None:
            return ()
        result = []
        seen_assets = set()
        for source, photos in (("room", room.photos), ("property", room.property.photos)):
            for photo in sorted(photos, key=lambda item: (item.position, item.id)):
                if photo.asset.status != "ready" or photo.media_asset_id in seen_assets:
                    continue
                result.append(self._photo_dto(photo, source))
                seen_assets.add(photo.media_asset_id)
        return tuple(result)

    def assess_room(
        self,
        db: Session,
        room_id: int,
        *,
        public_slug_candidate: str | None = None,
    ) -> RoomPublicationAssessment:
        room = self.repository.get_room_candidate(db, room_id)
        if room is None:
            return RoomPublicationAssessment(
                room_id=room_id,
                is_publicable=False,
                reasons=["room_not_found"],
            )

        reasons = []
        property_obj = room.property
        if not property_obj.active:
            reasons.append("property_inactive")
        if not property_obj.is_published:
            reasons.append("property_not_published")
        if not self._has_text(property_obj.public_title):
            reasons.append("property_public_title_required")
        if not self._has_text(property_obj.public_location):
            reasons.append("property_public_location_required")
        if not self._valid_slug(property_obj.public_slug):
            reasons.append("property_public_slug_required")
        if property_obj.manager is None or not property_obj.manager.active:
            reasons.append("property_manager_required")

        if not room.active:
            reasons.append("room_inactive")
        if not room.is_published:
            reasons.append("room_not_published")
        if not self._has_text(room.public_title):
            reasons.append("room_public_title_required")
        if not self._has_text(room.public_description):
            reasons.append("room_public_description_required")
        if not self._valid_slug(room.public_slug or public_slug_candidate):
            reasons.append("room_public_slug_required")
        if not self._price_is_valid(room.base_price):
            reasons.append("room_price_invalid")
        if self.room_capacity(room) is None:
            reasons.append("room_bed_capacity_required")
        if room.minimum_stay_months is None:
            reasons.append("room_minimum_stay_required")
        elif room.minimum_stay_months < 0:
            reasons.append("room_minimum_stay_negative")
        if room.maximum_stay_months is not None:
            if room.maximum_stay_months <= 0:
                reasons.append("room_maximum_stay_invalid")
            elif room.minimum_stay_months is not None and room.minimum_stay_months > 0 and room.maximum_stay_months < room.minimum_stay_months:
                reasons.append("room_stay_range_invalid")

        primary_photo = self._effective_primary_from_room(room)
        photo_source = primary_photo.source if primary_photo else None
        if primary_photo is None:
            reasons.append("public_photo_required")

        return RoomPublicationAssessment(
            room_id=room.id,
            is_publicable=not reasons,
            reasons=reasons,
            primary_photo_source=photo_source,
        )

    def list_feature_catalog(
        self,
        db: Session,
        *,
        active_only: bool = True,
    ) -> list[FeatureCatalogItem]:
        return [
            FeatureCatalogItem.model_validate(feature, from_attributes=True)
            for feature in self.repository.list_features(
                db, active_only=active_only
            )
        ]

    def get_public_availability(
        self,
        db: Session,
        room_id: int,
        *,
        today=None,
    ) -> PublicAvailability:
        today = today or business_today()
        intervals = self.repository.list_relevant_booking_intervals(
            db, room_id, today
        )
        room = self.repository.get_room_candidate(db, room_id)
        minimum = room.minimum_stay_months if room and room.minimum_stay_months is not None else 0
        status, available_from, available_until = first_commercial_gap(intervals, today, minimum)
        return PublicAvailability(
            status=status,
            available_from=available_from,
            available_until=available_until,
        )
