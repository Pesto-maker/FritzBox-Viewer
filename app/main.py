import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .fritzbox import run_connection_check
from .models import FetchStatus, LogEntry
from .scheduler import fetch_and_store_logs, start_scheduler
from . import config_store as cfg

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
# Externe Bibliotheken nicht auf DEBUG fluten
logging.getLogger("uvicorn").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    _scheduler = start_scheduler()
    yield
    if _scheduler:
        _scheduler.shutdown(wait=False)


app = FastAPI(title="FritzBox Viewer", lifespan=lifespan)

_templates_dir = os.path.join(os.path.dirname(__file__), "templates")
templates = Jinja2Templates(directory=_templates_dir)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ---------------------------------------------------------------------------
# REST API
# ---------------------------------------------------------------------------


@app.get("/api/logs")
def api_get_logs(
    db: Session = Depends(get_db),
    limit: int = Query(default=500, le=5000),
    offset: int = Query(default=0, ge=0),
    category: str | None = None,
    search: str | None = None,
    sort_by: str = "timestamp",
    sort_dir: str = "desc",
):
    allowed_sort_columns = {"timestamp", "message", "category"}
    if sort_by not in allowed_sort_columns:
        sort_by = "timestamp"

    query = db.query(LogEntry)

    if category:
        query = query.filter(LogEntry.category == category)
    if search:
        query = query.filter(LogEntry.message.ilike(f"%{search}%"))

    total = query.count()

    col = getattr(LogEntry, sort_by)
    query = query.order_by(col.desc() if sort_dir == "desc" else col.asc())
    entries = query.offset(offset).limit(limit).all()

    return {
        "total": total,
        "entries": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "message": e.message,
                "category": e.category,
            }
            for e in entries
        ],
    }


@app.get("/api/stats")
def api_stats(db: Session = Depends(get_db)):
    total = db.query(func.count(LogEntry.id)).scalar()
    by_category = (
        db.query(LogEntry.category, func.count(LogEntry.id))
        .group_by(LogEntry.category)
        .all()
    )
    status = db.query(FetchStatus).filter(FetchStatus.id == 1).first()

    return {
        "total": total,
        "by_category": {cat: cnt for cat, cnt in by_category},
        "last_fetch": status.last_fetch.isoformat() if status and status.last_fetch else None,
        "last_error": status.last_error if status else None,
    }


@app.post("/api/fetch")
def api_trigger_fetch():
    """Manually trigger a log fetch."""
    fetch_and_store_logs()
    return {"status": "ok"}


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "config": cfg.get_all_public(),
    })


@app.post("/api/admin/config")
def api_save_config(data: dict):
    """Save FritzBox connection settings."""
    allowed = {"fritz_host", "fritz_user", "fritz_password", "fetch_interval", "anthropic_api_key"}
    for key, value in data.items():
        if key in allowed:
            # Don't overwrite secrets if placeholder was sent
            if key in ("fritz_password", "anthropic_api_key") and set(value) == {"•"}:
                continue
            cfg.set(key, str(value).strip())
    return {"status": "ok"}


@app.post("/api/admin/fetch-with-sid")
def api_fetch_with_sid(data: dict, db: Session = Depends(get_db)):
    """Store manual SID and immediately fetch logs with it."""
    from .fritzbox import _fetch_eventlog_api
    from datetime import timezone
    import datetime as dt

    sid  = (data.get("sid") or "").strip()
    host = cfg.get("fritz_host")

    if not sid:
        return {"status": "error", "message": "SID darf nicht leer sein."}

    status = db.query(FetchStatus).filter(FetchStatus.id == 1).first()
    if not status:
        status = FetchStatus(id=1)
        db.add(status)

    try:
        entries = _fetch_eventlog_api(host, sid)
        new_count = 0
        for entry in entries:
            exists = db.query(LogEntry).filter(
                LogEntry.timestamp == entry["timestamp"],
                LogEntry.message   == entry["message"],
            ).first()
            if not exists:
                db.add(LogEntry(**entry))
                new_count += 1
        # Store SID for future automatic fetches
        cfg.set("manual_sid", sid)
        status.last_fetch = dt.datetime.now(timezone.utc)
        status.last_error = None
        status.total_fetched = (status.total_fetched or 0) + new_count
        db.commit()
        return {"status": "ok", "total_received": len(entries), "new_entries": new_count}
    except Exception as exc:
        status.last_error = str(exc)
        db.commit()
        return {"status": "error", "message": str(exc)}


@app.get("/recommendations", response_class=HTMLResponse)
def recommendations_page(request: Request):
    return templates.TemplateResponse("recommendations.html", {"request": request})


@app.post("/api/ai/analyze")
def api_ai_analyze(db: Session = Depends(get_db)):
    """Trigger AI analysis of recent logs."""
    from .ai_analyzer import run_analysis
    try:
        recs = run_analysis(db)
        return {"status": "ok", "count": len(recs)}
    except Exception as exc:
        logger.error("AI-Analyse fehlgeschlagen: %s", exc)
        return {"status": "error", "message": str(exc)}


@app.get("/api/ai/recommendations")
def api_get_recommendations(db: Session = Depends(get_db)):
    from .models import AiRecommendation
    recs = (
        db.query(AiRecommendation)
        .order_by(AiRecommendation.run_id.desc(), AiRecommendation.id.asc())
        .all()
    )
    return [
        {
            "id":          r.id,
            "run_id":      r.run_id,
            "created_at":  r.created_at.isoformat(),
            "title":       r.title,
            "description": r.description,
            "severity":    r.severity,
            "category":    r.category,
            "status":      r.status,
        }
        for r in recs
    ]


@app.patch("/api/ai/recommendations/{rec_id}")
def api_update_recommendation(rec_id: int, data: dict, db: Session = Depends(get_db)):
    from .models import AiRecommendation
    rec = db.query(AiRecommendation).filter(AiRecommendation.id == rec_id).first()
    if not rec:
        return {"status": "error", "message": "Nicht gefunden"}
    new_status = data.get("status")
    if new_status not in ("pending", "accepted", "rejected"):
        return {"status": "error", "message": "Ungültiger Status"}
    rec.status = new_status
    db.commit()
    return {"status": "ok"}


@app.get("/api/debug")
def api_debug():
    """
    Vollständiger Verbindungstest zur FritzBox.
    Zeigt jeden Schritt mit Erfolg/Fehler an.
    Aufruf: http://localhost:8000/api/debug
    """
    return run_connection_check()


@app.get("/api/debug/services")
def api_debug_services():
    """List all TR-064 services and their available actions."""
    from fritzconnection.core.fritzconnection import FritzConnection
    fc = FritzConnection(
        address=cfg.get("fritz_host"),
        user=cfg.get("fritz_user"),
        password=cfg.get("fritz_password"),
        timeout=10,
    )
    return {
        svc_name: sorted(svc.actions.keys())
        for svc_name, svc in fc.services.items()
    }
