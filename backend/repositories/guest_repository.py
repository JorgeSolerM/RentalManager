from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.guest import Guest
from backend.repositories.base_repository import BaseRepository


class GuestRepository(BaseRepository):

    def get_by_id(
        self,
        db: Session,
        guest_id: int,
    ) -> Guest | None:

        statement = (
            select(Guest)
            .where(Guest.id == guest_id)
        )

        return db.scalar(statement)

    def get_by_full_name(
        self,
        db: Session,
        full_name: str,
    ) -> Guest | None:

        statement = (
            select(Guest)
            .where(Guest.full_name == full_name)
        )

        return db.scalar(statement)
