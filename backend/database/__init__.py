from backend.models.property import Property

from backend.database.base import Base
from backend.database.session import engine


def init_db():

    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
    print("Base de datos creada correctamente.")
