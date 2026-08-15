from sqlalchemy.orm import Session

from backend.models.guest import Guest
from backend.repositories.guest_repository import GuestRepository


class GuestService:

    def __init__(self):

        self.guest_repository = GuestRepository()

    def get_guest(
        self,
        db: Session,
        guest_id: int,
    ) -> Guest | None:

        return self.guest_repository.get_by_id(
            db,
            guest_id,
        )

    def get_or_create_guest(
        self,
        db: Session,
        full_name: str,
    ) -> Guest:

        full_name = full_name.strip()

        try:
            guest = self.guest_repository.get_by_full_name(
                db,
                full_name,
            )

            if guest is None:
                guest = Guest(
                    full_name=full_name,
                    display_name=full_name,
                    active=True,
                )
                self.guest_repository.create(db, guest)

            db.commit()
            return guest
        except Exception:
            db.rollback()
            raise
