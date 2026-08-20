from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.models.media_asset import MediaAsset
from backend.models.property import Property
from backend.models.property_photo import PropertyPhoto
from backend.models.room import Room
from backend.models.room_photo import RoomPhoto


class PhotoRepository:
    def get_property(self, db: Session, property_id: int) -> Property | None:
        return db.scalar(select(Property).where(Property.id == property_id))

    def get_room(self, db: Session, room_id: int) -> Room | None:
        return db.scalar(select(Room).options(joinedload(Room.property)).where(Room.id == room_id))

    def list_property_photos(self, db: Session, property_id: int) -> list[PropertyPhoto]:
        return list(db.scalars(
            select(PropertyPhoto).options(joinedload(PropertyPhoto.asset))
            .where(PropertyPhoto.property_id == property_id)
            .order_by(PropertyPhoto.position, PropertyPhoto.id)
        ).all())

    def list_room_photos(self, db: Session, room_id: int) -> list[RoomPhoto]:
        return list(db.scalars(
            select(RoomPhoto).options(joinedload(RoomPhoto.asset))
            .where(RoomPhoto.room_id == room_id)
            .order_by(RoomPhoto.position, RoomPhoto.id)
        ).all())

    def get_property_photo(self, db: Session, photo_id: int) -> PropertyPhoto | None:
        return db.scalar(select(PropertyPhoto).options(joinedload(PropertyPhoto.asset)).where(PropertyPhoto.id == photo_id))

    def get_room_photo(self, db: Session, photo_id: int) -> RoomPhoto | None:
        return db.scalar(select(RoomPhoto).options(joinedload(RoomPhoto.asset)).where(RoomPhoto.id == photo_id))

    def get_asset(self, db: Session, asset_id: int) -> MediaAsset | None:
        return db.get(MediaAsset, asset_id)

    def get_asset_by_checksum(self, db: Session, checksum: str) -> MediaAsset | None:
        return db.scalar(select(MediaAsset).where(MediaAsset.checksum_sha256 == checksum))

    def next_property_position(self, db: Session, property_id: int) -> int:
        maximum = db.scalar(select(func.max(PropertyPhoto.position)).where(PropertyPhoto.property_id == property_id))
        return 0 if maximum is None else maximum + 1

    def next_room_position(self, db: Session, room_id: int) -> int:
        maximum = db.scalar(select(func.max(RoomPhoto.position)).where(RoomPhoto.room_id == room_id))
        return 0 if maximum is None else maximum + 1

    def asset_reference_count(self, db: Session, asset_id: int) -> int:
        properties = db.scalar(select(func.count(PropertyPhoto.id)).where(PropertyPhoto.media_asset_id == asset_id)) or 0
        rooms = db.scalar(select(func.count(RoomPhoto.id)).where(RoomPhoto.media_asset_id == asset_id)) or 0
        return properties + rooms

    @staticmethod
    def add(db: Session, instance) -> None:
        db.add(instance)
        db.flush()

    @staticmethod
    def delete(db: Session, instance) -> None:
        db.delete(instance)
        db.flush()
