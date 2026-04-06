import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase


def _db_path() -> str:
    """
    Pick a writable location for the SQLite database:
      - Frozen exe: %LOCALAPPDATA%\\FritzBox-Viewer\\  (per-user, always writable;
        the exe itself may live in C:\\Program Files\\ which is read-only).
        Falls back to the exe directory if LOCALAPPDATA is unset (rare).
      - Source checkout: project root (one level above this file).
    Returns a forward-slash path so it plugs cleanly into a SQLAlchemy URL
    on Windows (backslashes confuse the URL parser).
    """
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if appdata:
            base = os.path.join(appdata, "FritzBox-Viewer")
        else:
            base = os.path.dirname(sys.executable)
        os.makedirs(base, exist_ok=True)
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

    _migrate_encrypt_secrets()


def _migrate_encrypt_secrets():
    """Re-encrypt any plaintext secrets with Fernet (one-time migration)."""
    from .crypto import SECRET_KEYS, encrypt, _fernet
    from cryptography.fernet import InvalidToken

    with engine.connect() as conn:
        for key in SECRET_KEYS:
            row = conn.execute(
                text("SELECT value FROM app_config WHERE key = :k"),
                {"k": key},
            ).fetchone()
            if not row or not row[0]:
                continue
            val = row[0]
            # If decryption succeeds the value is already encrypted
            try:
                _fernet.decrypt(val.encode())
                continue
            except (InvalidToken, Exception):
                pass  # plaintext → encrypt it
            conn.execute(
                text("UPDATE app_config SET value = :v WHERE key = :k"),
                {"v": encrypt(val), "k": key},
            )
        conn.commit()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
