from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Directorio raíz del proyecto (C:\RentalManager)
BASE_DIR = Path(__file__).resolve().parents[2]

# Base de datos SQLite
DATABASE_PATH = BASE_DIR / "data" / "RentalManager.db"

DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)
