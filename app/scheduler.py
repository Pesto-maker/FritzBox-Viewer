import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from . import config_store
from .database import SessionLocal
from .fritzbox import get_fritzbox_logs
from .models import FetchStatus, LogEntry

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    """True once the user has stored FritzBox credentials in the Admin page."""
    return bool(config_store.get("fritz_password"))


def fetch_and_store_logs():
    """Fetch logs from FritzBox and persist new entries to the database."""
    if not is_configured():
        logger.info("Skipping log fetch — FritzBox not configured yet.")
        return
    logger.info("Starting FritzBox log fetch...")
    db = SessionLocal()
    status = db.query(FetchStatus).filter(FetchStatus.id == 1).first()
    if not status:
        status = FetchStatus(id=1)
        db.add(status)

    try:
        entries = get_fritzbox_logs()
        new_count = 0

        for entry in entries:
            exists = (
                db.query(LogEntry)
                .filter(
                    LogEntry.timestamp == entry["timestamp"],
                    LogEntry.message == entry["message"],
                )
                .first()
            )
            if not exists:
                db.add(LogEntry(**entry))
                new_count += 1

        status.last_fetch = datetime.now(timezone.utc)
        status.last_error = None
        status.total_fetched = (status.total_fetched or 0) + new_count
        db.commit()
        logger.info("Stored %d new log entries.", new_count)

    except Exception as exc:
        logger.error("Failed to fetch FritzBox logs: %s", exc, exc_info=True)
        status.last_error = str(exc)
        status.last_fetch = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    interval = int(config_store.get("fetch_interval") or 300)
    scheduler = BackgroundScheduler(timezone="UTC")
    # The job itself checks is_configured() on every run, so it is safe to
    # register it even before the user has entered credentials — once they
    # save their config in the Admin page the next tick will pick it up.
    scheduler.add_job(
        fetch_and_store_logs,
        trigger="interval",
        seconds=interval,
        next_run_time=datetime.now(timezone.utc),  # run immediately on startup
        id="fritzbox_fetch",
        name="FritzBox Log Fetch",
    )
    scheduler.start()
    if is_configured():
        logger.info("Scheduler started. Fetching every %d seconds.", interval)
    else:
        logger.info(
            "Scheduler started, but FritzBox is not configured yet — "
            "waiting for credentials via the Admin page."
        )
    return scheduler
