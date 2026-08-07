from pathlib import Path

from backend.database.base import Base
from backend.database.session import engine

# Registrar todos los modelos
import backend.models  # noqa: F401


def init_db():
    print("Engine:", engine.url)
    print("Base de datos:", Path("data/RentalManager.db").resolve())

    Base.metadata.create_all(bind=engine)

    db_path = Path("data/RentalManager.db")

    print("¿Existe el archivo?:", db_path.exists())


if __name__ == "__main__":
    init_db()
