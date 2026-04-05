import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase


def _db_path() -> str:
    """
    Always store the database next to the executable (or project root when
    running from source), never inside the PyInstaller temp extraction dir.
    Returns a forward-slash path so it plugs cleanly into a SQLAlchemy URL
    on Windows (backslashes confuse the URL parser).
    """
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "fritzbox_logs.db").replace("\\", "/")


SQLALCHEMY_DATABASE_URL = f"sqlite:///{_db_path()}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def run_migrations():
    """Drop legacy tables and apply incremental column additions."""
    with engine.connect() as conn:
        conn.execute(text("DROP TABLE IF EXISTS ai_recommendations"))
        # Add is_new column to ai_comments if it doesn't exist yet
        try:
            conn.execute(text("ALTER TABLE ai_comments ADD COLUMN is_new BOOLEAN DEFAULT 0"))
        except Exception:
            pass  # Column already exists
        conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
