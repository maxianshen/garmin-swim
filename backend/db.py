"""Database engine and session management."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DEFAULT_DB_PATH = Path(os.environ.get("GARMIN_DATA_DIR", Path(__file__).parent.parent)) / "garmin.db"
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DEFAULT_DB_PATH.resolve()}")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    """Create all tables if they do not exist."""
    import models  # noqa: F401

    if DATABASE_URL.startswith("sqlite"):
        db_path = DATABASE_URL.replace("sqlite:///", "", 1)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
