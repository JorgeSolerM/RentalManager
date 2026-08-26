from datetime import date
from decimal import Decimal
import re
from collections.abc import Callable
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from backend.core.business_time import business_today
from backend.core.public_availability import (
    first_commercial_gap,
    stay_within_calendar_month_limits,
)
from backend.core.public_phone import whatsapp_url
from backend.services.publication_service import PUBLIC_SLUG_PATTERN
from backend.services.publication_service import PublicationService
from backend.public.repository import PublicRoomRepository
from backend.public.schemas import (
    PublicAvailabilityDTO,
    PublicFeatureDTO,
    PublicFilterFeatureDTO,
    PublicFeatureGroupDTO,
    PublicImageDTO,
    PublicHousingRuleDTO,
    PublicManagerDTO,
    PublicManagerPhotoDTO,
    PublicRoomCardDTO,
    PublicRoomDetailDTO,
    PublicRequirementDTO,
    PublicTenantAgeDTO,
)


ImageUrlBuilder = Callable[[str, int], str]


CATEGORY_PRESENTATION = {
    "Dormitorio": (10, "bed.svg"),
    "Mobiliario": (20, "furniture.svg"),
    "Climatización": (30, "climate.svg"),
    "Conectividad": (40, "wifi.svg"),
    "Privado": (50, "private.svg"),
    "Equipamiento común": (60, "home.svg"),
    "Edificio": (70, "building.svg"),
    "Zonas comunes": (80, "shared.svg"),
    "Condiciones": (90, "conditions.svg"),
}


class PublicRoomService:
    SORT_OPTIONS = {
        "recommended",
        "price_asc",
        "price_desc",
        "availability",
        "size_asc",
        "size_desc",
    }

    def __init__(
        self,
        repository: PublicRoomRepository | None = None,
        image_url_builder: ImageUrlBuilder | None = None,
    ):
        self.repository = repository or PublicRoomRepository()
        self.image_url_builder = image_url_builder or (
            lambda storage_key, width: f"/media/{storage_key}/{width}.webp"
        )

    def list_rooms(
        self,
        db: Session,
        *,
        today: date | None = None,
        requested_check_in: date | None = None,
        requested_check_out: date | None = None,
        feature_slugs: tuple[str, ...] = (),
        public_base_url: str | None = None,
        sort: str = "recommended",
    ) -> tuple[PublicRoomCardDTO, ...]:
        today = today or business_today()
        result = []
        for room in self.repository.list_candidates(
            db,
            today,
            requested_check_in=requested_check_in,
            requested_check_out=requested_check_out,
            feature_slugs=feature_slugs,
        ):
            if self._is_publicable(room) and (
                requested_check_in is None
                or stay_within_calendar_month_limits(
                    requested_check_in,
                    requested_check_out,
                    room.minimum_stay_months,
                    room.maximum_stay_months,
                )
            ):
                result.append(self._card(room, today, public_base_url))
        return tuple(sorted(result, key=self._sort_key(sort, today)))

    @classmethod
    def normalize_sort(cls, value: str | None) -> str:
        return value if value in cls.SORT_OPTIONS else "recommended"

    @classmethod
    def _sort_key(cls, sort: str, today: date):
        sort = cls.normalize_sort(sort)

        def availability(room: PublicRoomCardDTO):
            available_from = room.availability.available_from or today
            status_rank = 0 if room.availability.status == "available_now" else 1
            return available_from, status_rank

        def surface(room: PublicRoomCardDTO):
            return (
                room.square_meters is None,
                room.square_meters if room.square_meters is not None else Decimal(0),
            )

        def descending_surface(room: PublicRoomCardDTO):
            missing, value = surface(room)
            return missing, -value

        if sort == "price_asc":
            return lambda room: (room.price_monthly, availability(room), room.slug)
        if sort == "price_desc":
            return lambda room: (-room.price_monthly, availability(room), room.slug)
        if sort == "availability":
            return lambda room: (availability(room), room.price_monthly, room.slug)
        if sort == "size_asc":
            return lambda room: (surface(room), room.price_monthly, room.slug)
        if sort == "size_desc":
            return lambda room: (descending_surface(room), room.price_monthly, room.slug)
        return lambda room: (
            availability(room),
            room.price_monthly,
            surface(room),
            room.slug,
        )

    def list_filter_features(
        self, db: Session
    ) -> tuple[PublicFilterFeatureDTO, ...]:
        return tuple(
            PublicFilterFeatureDTO(
                slug=feature.slug,
                name=feature.name,
                category=feature.category,
            )
            for feature in self.repository.list_filter_features(db)
        )

    def get_room(
        self, db: Session, slug: str, *, today: date | None = None,
        public_base_url: str | None = None,
    ) -> PublicRoomDetailDTO | None:
        today = today or business_today()
        room = self.repository.get_candidate_by_slug(db, slug, today)
        if room is None or not self._is_publicable(room):
            return None
        card = self._card(room, today, public_base_url)
        room_features = self._features(room.features)
        property_features = self._features(room.property.features)
        highlighted_features = card.features
        description = room.public_description.strip()
        has_private_bathroom = any(
            feature.active and feature.slug == "bano-privado"
            for feature in room.features
        )
        property_rooms = self.repository.list_property_candidates(
            db, room.property_id, today
        )
        return PublicRoomDetailDTO(
            **card.model_dump(),
            description=description,
            map_url=self._map_url(room.property),
            minimum_stay_months=room.minimum_stay_months,
            maximum_stay_months=room.maximum_stay_months,
            flatmates_count=self._flatmates_count(room, property_rooms),
            tenant_gender_preference=(room.tenant_gender_preference or "any"),
            room_features=room_features,
            property_features=property_features,
            feature_groups=self._feature_groups(room),
            highlighted_features=highlighted_features,
            housing_rules=self._housing_rules(room),
            tenant_age=self._tenant_age(room.property),
            requirements=self._requirements(room.property),
            has_private_bathroom=has_private_bathroom,
            shared_full_bathroom_count=room.property.shared_full_bathroom_count,
            shared_toilet_count=room.property.shared_toilet_count,
            manager=self._manager(room.property.manager, room, public_base_url),
            gallery=self._gallery(room),
            meta_description=self._meta_description(description),
        )

    @staticmethod
    def _housing_rules(room) -> tuple[PublicHousingRuleDTO, ...]:
        property_obj = room.property
        double_bed = any(
            feature.active and feature.slug == "cama-doble"
            for feature in room.features
        )
        configured = (
            (property_obj.smoking_allowed, "Se permite fumar", "No se permite fumar"),
            (property_obj.pets_allowed, "Se permiten mascotas", "No se permiten mascotas"),
            (double_bed, "Se admiten parejas", "No se admiten parejas"),
            (
                property_obj.musical_instruments_allowed,
                "Se permiten instrumentos musicales",
                "No se permiten instrumentos musicales",
            ),
        )
        return tuple(
            PublicHousingRuleDTO(
                label=positive if value else negative,
                allowed=value,
            )
            for value, positive, negative in configured
            if value is not None
        )

    @staticmethod
    def _tenant_age(property_obj) -> PublicTenantAgeDTO | None:
        if (
            property_obj.minimum_tenant_age is None
            and property_obj.maximum_tenant_age is None
        ):
            return None
        return PublicTenantAgeDTO(
            minimum=property_obj.minimum_tenant_age,
            maximum=property_obj.maximum_tenant_age,
        )

    @staticmethod
    def _requirements(property_obj) -> tuple[PublicRequirementDTO, ...]:
        return tuple(
            PublicRequirementDTO(
                name=requirement.public_name,
                description=requirement.public_description,
            )
            for requirement in sorted(
                (item for item in property_obj.requirements if item.active),
                key=lambda item: (item.display_order, item.public_name.casefold()),
            )
        )

    @staticmethod
    def _has_text(value: str | None) -> bool:
        return bool(value and value.strip())

    def _is_publicable(self, room) -> bool:
        property_obj = room.property
        if not (
            property_obj.active
            and property_obj.is_published
            and self._has_text(property_obj.public_title)
            and self._has_text(property_obj.public_location)
            and property_obj.public_slug
            and PUBLIC_SLUG_PATTERN.fullmatch(property_obj.public_slug)
            and property_obj.manager is not None
            and property_obj.manager.active
            and room.active
            and room.operational_since is not None
            and room.is_published
            and self._has_text(room.public_title)
            and self._has_text(room.public_description)
            and room.public_slug
            and PUBLIC_SLUG_PATTERN.fullmatch(room.public_slug)
            and room.base_price is not None
            and Decimal(room.base_price).is_finite()
            and Decimal(room.base_price) > 0
            and room.minimum_stay_months is not None
            and room.minimum_stay_months >= 0
            and (room.maximum_stay_months is None or room.maximum_stay_months > 0)
            and (
                room.maximum_stay_months is None
                or room.minimum_stay_months == 0
                or room.maximum_stay_months >= room.minimum_stay_months
            )
        ):
            return False
        if PublicationService.room_capacity(room) is None:
            return False
        return self._primary_photo(room) is not None

    def _flatmates_count(self, current_room, property_rooms) -> int:
        return sum(
            capacity
            for sibling in property_rooms
            if sibling.id != current_room.id and self._is_publicable(sibling)
            if (capacity := PublicationService.room_capacity(sibling)) is not None
        )

    def _card(
        self, room, today: date, public_base_url: str | None = None
    ) -> PublicRoomCardDTO:
        primary = self._primary_photo(room)
        return PublicRoomCardDTO(
            slug=room.public_slug,
            title=room.public_title.strip(),
            location=room.property.public_location.strip(),
            price_monthly=room.base_price,
            square_meters=room.square_meters,
            availability=self._availability(room.bookings, today, room.minimum_stay_months),
            features=self._highlighted_features(room),
            primary_image=self._image(primary, self._photo_source(room, primary)),
            contact_url=self._manager(
                room.property.manager, room, public_base_url
            ).whatsapp_url,
        )

    @staticmethod
    def _highlighted_features(room) -> tuple[PublicFeatureDTO, ...]:
        return tuple(
            PublicFeatureDTO(
                name=highlight.feature.name,
                category=highlight.feature.category,
                icon_key=highlight.feature.icon_key,
            )
            for highlight in room.public_highlights
            if highlight.feature.active
        )

    @staticmethod
    def _features(features) -> tuple[PublicFeatureDTO, ...]:
        return tuple(
            PublicFeatureDTO(
                name=feature.name,
                category=feature.category,
                icon_key=feature.icon_key,
            )
            for feature in sorted(
                (feature for feature in features if feature.active),
                key=lambda item: (item.category, item.display_order, item.name),
            )
        )

    @staticmethod
    def _feature_groups(room) -> tuple[PublicFeatureGroupDTO, ...]:
        effective = {}
        for feature in (*room.features, *room.property.features):
            if feature.active and feature.slug != "bano-privado":
                effective.setdefault(feature.id, feature)

        grouped = {}
        for feature in effective.values():
            grouped.setdefault(feature.category, []).append(feature)

        def category_key(category):
            configured = CATEGORY_PRESENTATION.get(category)
            return (configured[0], "") if configured else (1000, category.casefold())

        result = []
        for category in sorted(grouped, key=category_key):
            icon = CATEGORY_PRESENTATION.get(category, (1000, "generic.svg"))[1]
            features = sorted(
                grouped[category],
                key=lambda feature: (feature.display_order, feature.name.casefold()),
            )
            result.append(PublicFeatureGroupDTO(
                category=category,
                icon_url=f"/static/icons/feature-categories/{icon}",
                features=tuple(PublicFeatureDTO(
                    name=feature.name,
                    category=feature.category,
                    icon_key=feature.icon_key,
                ) for feature in features),
            ))
        return tuple(result)

    @staticmethod
    def _primary_photo(room):
        own = next(
            (
                photo
                for photo in room.photos
                if photo.is_primary and photo.asset.status == "ready"
            ),
            None,
        )
        if own is not None:
            return own
        return next(
            (
                photo
                for photo in room.property.photos
                if photo.is_primary and photo.asset.status == "ready"
            ),
            None,
        )

    @staticmethod
    def _photo_source(room, photo) -> str:
        return "room" if getattr(photo, "room_id", None) == room.id else "property"

    def _gallery(self, room) -> tuple[PublicImageDTO, ...]:
        result = []
        seen_assets = set()
        for source, photos in (
            ("room", room.photos),
            ("property", room.property.photos),
        ):
            for photo in sorted(photos, key=lambda item: (item.position, item.id)):
                if photo.asset.status != "ready" or photo.media_asset_id in seen_assets:
                    continue
                result.append(self._image(photo, source))
                seen_assets.add(photo.media_asset_id)
        return tuple(result)

    def _image(self, photo, source: str) -> PublicImageDTO:
        key = photo.asset.storage_key
        return PublicImageDTO(
            url_320=self.image_url_builder(key, 320),
            url_768=self.image_url_builder(key, 768),
            url_1600=self.image_url_builder(key, 1600),
            source=source,
            width=photo.asset.width,
            height=photo.asset.height,
        )

    def _manager(self, manager, room, public_base_url: str | None) -> PublicManagerDTO:
        words = manager.name.split()
        initials = "".join(word[0] for word in words[:2]).upper()
        photo = None
        if manager.photo is not None and manager.photo.status == "ready":
            key = manager.photo.storage_key
            photo = PublicManagerPhotoDTO(
                url_320=self.image_url_builder(key, 320),
                url_768=self.image_url_builder(key, 768),
                url_1600=self.image_url_builder(key, 1600),
                width=manager.photo.width,
                height=manager.photo.height,
            )
        contact_url = None
        if public_base_url and manager.active and manager.phone:
            listing_url = f"{public_base_url.rstrip('/')}/habitaciones/{room.public_slug}"
            message = (
                f'Hola, estoy interesado en la habitación "{room.public_title.strip()}".'
                f"\n\n{listing_url}"
            )
            contact_url = whatsapp_url(manager.phone, message)
        return PublicManagerDTO(
            name=manager.name,
            initials=initials,
            photo=photo,
            whatsapp_url=contact_url,
        )

    @staticmethod
    def _map_url(property_obj) -> str | None:
        street = property_obj.street.strip() if property_obj.street else ""
        city = property_obj.city.strip() if property_obj.city else ""
        if not street or not city:
            return None
        street_number = (
            property_obj.street_number.strip()
            if property_obj.street_number
            else ""
        )
        street_line = " ".join(part for part in (street, street_number) if part)
        query = f"{street_line}, {city}"
        return "https://www.google.com/maps/search/?" + urlencode({
            "api": "1",
            "query": query,
        })

    @staticmethod
    def _availability(bookings, today: date, minimum_stay_months: int) -> PublicAvailabilityDTO:
        status, available_from, available_until = first_commercial_gap(
            ((booking.check_in, booking.check_out) for booking in bookings),
            today,
            minimum_stay_months,
        )
        return PublicAvailabilityDTO(
            status=status,
            available_from=available_from,
            available_until=available_until,
        )

    @staticmethod
    def _meta_description(description: str) -> str:
        normalized = re.sub(r"\s+", " ", description).strip()
        return normalized if len(normalized) <= 155 else normalized[:152].rstrip() + "…"
