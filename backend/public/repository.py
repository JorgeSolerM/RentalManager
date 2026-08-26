from datetime import date

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session, joinedload, load_only, selectinload

from backend.models.booking import Booking
from backend.models.feature import Feature, property_features, room_features
from backend.models.media_asset import MediaAsset
from backend.models.manager import Manager
from backend.models.property import Property
from backend.models.property_photo import PropertyPhoto
from backend.models.room import Room
from backend.models.room_photo import RoomPhoto
from backend.models.room_public_highlight import RoomPublicHighlight
from backend.models.rental_requirement import RentalRequirement


class PublicRoomRepository:
    @staticmethod
    def _load_options(today: date):
        return (
            load_only(
                Room.id,
                Room.property_id,
                Room.active,
                Room.operational_since,
                Room.base_price,
                Room.square_meters,
                Room.minimum_stay_months,
                Room.maximum_stay_months,
                Room.tenant_gender_preference,
                Room.public_title,
                Room.public_description,
                Room.public_slug,
                Room.is_published,
            ),
            joinedload(Room.property)
            .load_only(
                Property.id,
                Property.active,
                Property.public_title,
                Property.public_location,
                Property.public_slug,
                Property.is_published,
                Property.smoking_allowed,
                Property.pets_allowed,
                Property.musical_instruments_allowed,
                Property.minimum_tenant_age,
                Property.maximum_tenant_age,
                Property.shared_full_bathroom_count,
                Property.shared_toilet_count,
            )
            .selectinload(Property.features)
            .load_only(
                Feature.id,
                Feature.slug,
                Feature.name,
                Feature.category,
                Feature.icon_key,
                Feature.display_order,
                Feature.active,
            ),
            joinedload(Room.property)
            .selectinload(Property.requirements)
            .load_only(
                RentalRequirement.id,
                RentalRequirement.public_name,
                RentalRequirement.public_description,
                RentalRequirement.active,
                RentalRequirement.display_order,
            ),
            joinedload(Room.property)
            .joinedload(Property.manager)
            .load_only(Manager.id, Manager.name, Manager.phone, Manager.active, Manager.media_asset_id)
            .joinedload(Manager.photo)
            .load_only(
                MediaAsset.id,
                MediaAsset.storage_key,
                MediaAsset.status,
                MediaAsset.width,
                MediaAsset.height,
            ),
            joinedload(Room.property)
            .load_only(
                Property.id,
                Property.active,
                Property.public_title,
                Property.public_location,
                Property.public_slug,
                Property.is_published,
            )
            .selectinload(Property.photos)
            .joinedload(PropertyPhoto.asset)
            .load_only(
                MediaAsset.id,
                MediaAsset.storage_key,
                MediaAsset.status,
                MediaAsset.width,
                MediaAsset.height,
            ),
            selectinload(Room.features).load_only(
                Feature.id,
                Feature.slug,
                Feature.name,
                Feature.category,
                Feature.icon_key,
                Feature.display_order,
                Feature.active,
            ),
            joinedload(Room.public_highlights)
            .joinedload(RoomPublicHighlight.feature)
            .load_only(
                Feature.id,
                Feature.name,
                Feature.category,
                Feature.icon_key,
                Feature.active,
            ),
            selectinload(Room.photos)
            .joinedload(RoomPhoto.asset)
            .load_only(
                MediaAsset.id,
                MediaAsset.storage_key,
                MediaAsset.status,
                MediaAsset.width,
                MediaAsset.height,
            ),
            selectinload(Room.bookings.and_(Booking.check_out > today)).load_only(
                Booking.id,
                Booking.room_id,
                Booking.check_in,
                Booking.check_out,
            ),
        )

    def list_candidates(
        self,
        db: Session,
        today: date,
        *,
        requested_check_in: date | None = None,
        requested_check_out: date | None = None,
        feature_slugs: tuple[str, ...] = (),
    ) -> list[Room]:
        statement = (
            select(Room)
            .join(Room.property)
            .options(*self._load_options(today))
            .where(
                Room.active.is_(True),
                Room.operational_since.is_not(None),
                Room.is_published.is_(True),
                Property.active.is_(True),
                Property.is_published.is_(True),
            )
            .order_by(Property.public_location, Room.public_title, Room.public_slug)
        )
        if requested_check_in is not None and requested_check_out is not None:
            statement = statement.where(
                ~exists(
                    select(Booking.id).where(
                        Booking.room_id == Room.id,
                        Booking.check_in < requested_check_out,
                        Booking.check_out > requested_check_in,
                    )
                )
            )
        for slug in feature_slugs:
            room_has_feature = exists(
                select(room_features.c.feature_id)
                .join(Feature, Feature.id == room_features.c.feature_id)
                .where(
                    room_features.c.room_id == Room.id,
                    Feature.slug == slug,
                    Feature.active.is_(True),
                )
            )
            property_has_feature = exists(
                select(property_features.c.feature_id)
                .join(Feature, Feature.id == property_features.c.feature_id)
                .where(
                    property_features.c.property_id == Room.property_id,
                    Feature.slug == slug,
                    Feature.active.is_(True),
                )
            )
            statement = statement.where(or_(room_has_feature, property_has_feature))
        return list(db.scalars(statement).unique().all())

    def list_filter_features(self, db: Session) -> list[Feature]:
        room_assignment = exists(
            select(room_features.c.feature_id)
            .join(Room, Room.id == room_features.c.room_id)
            .join(Property, Property.id == Room.property_id)
            .where(
                room_features.c.feature_id == Feature.id,
                Room.active.is_(True),
                Room.operational_since.is_not(None),
                Room.is_published.is_(True),
                Property.active.is_(True),
                Property.is_published.is_(True),
            )
        )
        property_assignment = exists(
            select(property_features.c.feature_id)
            .join(Property, Property.id == property_features.c.property_id)
            .join(Room, Room.property_id == Property.id)
            .where(
                property_features.c.feature_id == Feature.id,
                Room.active.is_(True),
                Room.operational_since.is_not(None),
                Room.is_published.is_(True),
                Property.active.is_(True),
                Property.is_published.is_(True),
            )
        )
        statement = (
            select(Feature)
            .where(
                Feature.active.is_(True),
                or_(room_assignment, property_assignment),
            )
            .order_by(Feature.category, Feature.display_order, Feature.name)
        )
        return list(db.scalars(statement).all())

    def get_candidate_by_slug(
        self, db: Session, slug: str, today: date
    ) -> Room | None:
        statement = (
            select(Room)
            .join(Room.property)
            .options(
                *self._load_options(today),
                joinedload(Room.property).load_only(
                    Property.id,
                    Property.street,
                    Property.street_number,
                    Property.city,
                ),
            )
            .where(Room.public_slug == slug)
        )
        return db.scalars(statement).unique().one_or_none()

    def list_property_candidates(
        self, db: Session, property_id: int, today: date
    ) -> list[Room]:
        statement = (
            select(Room)
            .join(Room.property)
            .options(*self._load_options(today))
            .where(
                Room.property_id == property_id,
                Room.active.is_(True),
                Room.operational_since.is_not(None),
                Room.is_published.is_(True),
                Property.active.is_(True),
                Property.is_published.is_(True),
            )
            .order_by(Room.display_order, Room.code)
        )
        return list(db.scalars(statement).unique().all())
