from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

SQLALCHEMY_DATABASE_URL = "sqlite:///./fritzbox_logs.db"

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
