from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from backend.models.manager import Manager
from backend.models.media_asset import MediaAsset
from backend.models.property import Property


class ManagerRepository:
    def list_all(self, db: Session) -> list[Manager]:
        return list(db.scalars(
            select(Manager).options(joinedload(Manager.photo)).order_by(Manager.name, Manager.id)
        ).all())

    def get(self, db: Session, manager_id: int) -> Manager | None:
        return db.scalar(
            select(Manager).options(joinedload(Manager.photo)).where(Manager.id == manager_id)
        )

    def active_options(self, db: Session, selected_id: int | None = None) -> list[Manager]:
        statement = select(Manager).where(Manager.active.is_(True))
        if selected_id is not None:
            statement = select(Manager).where(
                (Manager.active.is_(True)) | (Manager.id == selected_id)
            )
        return list(db.scalars(statement.order_by(Manager.name, Manager.id)).all())

    def assign_unassigned(self, db: Session, manager_id: int) -> int:
        result = db.execute(
            update(Property).where(Property.manager_id.is_(None)).values(manager_id=manager_id)
        )
        return result.rowcount or 0

    @staticmethod
    def asset_by_checksum(db: Session, checksum: str) -> MediaAsset | None:
        return db.scalar(select(MediaAsset).where(MediaAsset.checksum_sha256 == checksum))
