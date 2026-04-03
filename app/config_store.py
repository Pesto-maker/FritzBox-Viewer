"""
DB-backed configuration store.
Priority: DB value → .env / environment variable → default
"""
import os
from .database import SessionLocal
from .models import AppConfig

_DEFAULTS = {
    "fritz_host":      ("FRITZ_HOST",     "fritz.box"),
    "fritz_user":      ("FRITZ_USER",     ""),
    "fritz_password":  ("FRITZ_PASSWORD", ""),
    "fetch_interval":  ("FETCH_INTERVAL", "300"),
    "manual_sid":      (None,             ""),
}


def get(key: str) -> str:
    db = SessionLocal()
    try:
        row = db.query(AppConfig).filter(AppConfig.key == key).first()
        if row and row.value is not None:
            return row.value
    finally:
        db.close()
    env_key, default = _DEFAULTS.get(key, (None, ""))
    if env_key:
        return os.getenv(env_key, default)
    return default


def set(key: str, value: str):
    db = SessionLocal()
    try:
        row = db.query(AppConfig).filter(AppConfig.key == key).first()
        if row:
            row.value = value
        else:
            db.add(AppConfig(key=key, value=value))
        db.commit()
    finally:
        db.close()


def get_all_public() -> dict:
    """Return all config values (password masked)."""
    return {
        "fritz_host":     get("fritz_host"),
        "fritz_user":     get("fritz_user"),
        "fritz_password": "••••••••" if get("fritz_password") else "",
        "fetch_interval": get("fetch_interval"),
        "manual_sid":     get("manual_sid"),
    }
