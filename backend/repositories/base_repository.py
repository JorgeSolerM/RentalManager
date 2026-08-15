from sqlalchemy.orm import Session


class BaseRepository:

    def create(
        self,
        db: Session,
        entity,
    ):

        db.add(entity)
        db.flush()

        return entity

    def update(
        self,
        db: Session,
        entity,
    ):

        db.add(entity)
        db.flush()

        return entity

    def delete(
        self,
        db: Session,
        entity,
    ) -> None:

        db.delete(entity)
        db.flush()
