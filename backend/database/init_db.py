from pathlib import Path

from backend.database.session import engine


def init_db():
    """Report the configured database without changing its schema."""
    print("Engine:", engine.url)
    print("Base de datos:", Path("data/RentalManager.db").resolve())

    db_path = Path("data/RentalManager.db")

    print("¿Existe el archivo?:", db_path.exists())


if __name__ == "__main__":
    init_db()
