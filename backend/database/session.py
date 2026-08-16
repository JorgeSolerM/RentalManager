from pathlib import Path
import sqlite3

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Directorio raíz del proyecto (C:\RentalManager)
BASE_DIR = Path(__file__).resolve().parents[2]

# Base de datos SQLite
DATABASE_PATH = BASE_DIR / "data" / "RentalManager.db"

DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"


@event.listens_for(Engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
        finally:
            cursor.close()


engine = create_engine(
    DATABASE_URL,
    echo=False,  # Cambiar a True para depuración SQL
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db():
    db: Session = SessionLocal()

    try:
        yield db
    finally:
        db.close()
