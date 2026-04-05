import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import Base, engine, get_db, run_migrations
from .fritzbox import run_connection_check
from .models import FetchStatus, LogEntry, AiProblem, AiMeasure, AiComment
from .scheduler import fetch_and_store_logs, start_scheduler
from . import config_store as cfg

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_debug = os.environ.get("FRITZ_DEBUG") == "1"
logging.basicConfig(
    level=logging.DEBUG if _debug else logging.WARNING,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
if _debug:
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
logger = logging.getLogger(__name__)

run_migrations()
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


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "config": cfg.get_all_public(),
    })


@app.get("/recommendations")
def recommendations_redirect():
    return RedirectResponse(url="/")


@app.get("/problems/{problem_id}", response_class=HTMLResponse)
def problem_detail(problem_id: int, request: Request):
    return templates.TemplateResponse("problem_detail.html", {
        "request": request,
        "problem_id": problem_id,
    })


# ---------------------------------------------------------------------------
# Logs API
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
    fetch_and_store_logs()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Admin API
# ---------------------------------------------------------------------------


@app.post("/api/admin/config")
def api_save_config(data: dict):
    allowed = {"fritz_host", "fritz_user", "fritz_password", "fetch_interval",
               "anthropic_api_key", "system_prompt_logs", "system_prompt_full"}
    for key, value in data.items():
        if key in allowed:
            if key in ("fritz_password", "anthropic_api_key") and set(value) == {"•"}:
                continue
            cfg.set(key, str(value).strip())
    return {"status": "ok"}


@app.post("/api/admin/fetch-with-sid")
def api_fetch_with_sid(data: dict, db: Session = Depends(get_db)):
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


# ---------------------------------------------------------------------------
# Export API
# ---------------------------------------------------------------------------


@app.get("/api/export/logs", response_class=PlainTextResponse)
def api_export_logs(db: Session = Depends(get_db)):
    """Export log entries as plain text for upload to AI chat."""
    from datetime import timezone
    import datetime as dt

    entries = db.query(LogEntry).order_by(LogEntry.timestamp.asc()).all()

    lines = [
        f"FritzBox Ereignisprotokoll — Export {dt.datetime.now(timezone.utc).strftime('%d.%m.%Y %H:%M')} UTC",
        f"Einträge gesamt: {len(entries)}",
        "=" * 70,
        "",
    ]
    for e in entries:
        lines.append(f"{e.timestamp.strftime('%d.%m.%y %H:%M:%S')}  [{e.category:<10}]  {e.message}")

    filename = dt.datetime.now(timezone.utc).strftime("fritzbox_logs_%Y%m%d_%H%M.txt")
    return PlainTextResponse(
        content="\n".join(lines),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/export/full", response_class=PlainTextResponse)
def api_export_full(db: Session = Depends(get_db)):
    """Export logs + all problems and measures with status and comments."""
    from datetime import timezone
    import datetime as dt

    now_str = dt.datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M")

    # Logs
    entries = db.query(LogEntry).order_by(LogEntry.timestamp.asc()).all()

    # Problems grouped by run_id
    problems = (
        db.query(AiProblem)
        .order_by(AiProblem.run_id.desc(), AiProblem.id.asc())
        .all()
    )
    measures = db.query(AiMeasure).all()
    all_comments = db.query(AiComment).order_by(AiComment.created_at.asc()).all()

    measures_by_problem: dict[int, list] = {}
    for m in measures:
        measures_by_problem.setdefault(m.problem_id, []).append(m)

    comments_by_parent: dict[tuple, list] = {}
    for c in all_comments:
        key = (c.parent_type, c.parent_id)
        comments_by_parent.setdefault(key, []).append(c)

    SEV_LABEL = {"critical": "KRITISCH", "warning": "WARNUNG", "info": "INFO"}
    STATUS_LABEL = {
        "pending": "offen",
        "check":   "in Prüfung (Wirksamkeit prüfen)",
        "rejected": "abgelehnt",
        "success": "erfolgreich umgesetzt",
        "failed": "umgesetzt, nicht erfolgreich",
    }

    def fmt_comments(parent_type, parent_id, indent):
        clist = comments_by_parent.get((parent_type, parent_id), [])
        if not clist:
            return []
        out = [f"{indent}Kommentare:"]
        for c in clist:
            ts = c.created_at.strftime("%d.%m.%y %H:%M")
            out.append(f"{indent}  [{ts}] {c.text}")
        return out

    lines = [
        "=== FritzBox Viewer — Vollständiger Export ===",
        f"Exportiert am: {now_str} UTC",
        "",
        f"=== PROTOKOLLEINTRÄGE ({len(entries)} Einträge, chronologisch) ===",
        "",
    ]
    for e in entries:
        lines.append(f"{e.timestamp.strftime('%d.%m.%y %H:%M:%S')}  [{e.category:<10}]  {e.message}")

    lines += ["", "=" * 70, "", "=== PROBLEME & MAßNAHMEN ==="]

    if not problems:
        lines += ["", "(Noch keine Probleme erfasst)"]
    else:
        run_ids: list[int] = []
        probs_by_run: dict[int, list] = {}
        for p in problems:
            if p.run_id not in probs_by_run:
                run_ids.append(p.run_id)
                probs_by_run[p.run_id] = []
            probs_by_run[p.run_id].append(p)

        for run_id in run_ids:
            run_dt = dt.datetime.fromtimestamp(run_id, tz=timezone.utc).strftime("%d.%m.%Y %H:%M")
            lines += ["", f"--- Analyse vom {run_dt} UTC ---"]
            for p in probs_by_run[run_id]:
                sev = SEV_LABEL.get(p.severity, p.severity.upper())
                status_lbl = STATUS_LABEL.get(p.status, p.status)
                lines += [
                    "",
                    f"[{sev}] {p.title}",
                    f"  Status: {status_lbl}",
                    f"  Identifiziert am: {p.created_at.strftime('%d.%m.%Y %H:%M:%S')} UTC",
                    f"  Kategorie: {p.category or '-'}",
                    f"  Beschreibung: {p.description}",
                ]
                lines += fmt_comments("problem", p.id, "  ")
                p_measures = measures_by_problem.get(p.id, [])
                if p_measures:
                    lines.append("  Maßnahmen:")
                    for i, m in enumerate(p_measures, 1):
                        m_status = STATUS_LABEL.get(m.status, m.status)
                        lines += [
                            f"  [{i}] {m.title}",
                            f"      Status: {m_status}",
                            f"      Beschreibung: {m.description}",
                        ]
                        lines += fmt_comments("measure", m.id, "      ")

    filename = dt.datetime.now(timezone.utc).strftime("fritzbox_vollexport_%Y%m%d_%H%M.txt")
    return PlainTextResponse(
        content="\n".join(lines),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# System Prompts API
# ---------------------------------------------------------------------------


@app.get("/api/ai/system-prompts")
def api_get_system_prompts():
    """Return the currently configured system prompts."""
    return {
        "logs": cfg.get("system_prompt_logs"),
        "full": cfg.get("system_prompt_full"),
    }


@app.get("/api/ai/system-prompts/default")
def api_get_default_system_prompts():
    """Return the built-in default system prompts (for reset button)."""
    from . import config_store as _cs
    return {
        "system_prompt_logs": _cs.DEFAULT_SYSTEM_PROMPT_LOGS,
        "system_prompt_full": _cs.DEFAULT_SYSTEM_PROMPT_FULL,
    }


# ---------------------------------------------------------------------------
# AI Analysis API
# ---------------------------------------------------------------------------


@app.post("/api/ai/import")
def api_ai_import(data: dict, db: Session = Depends(get_db)):
    """Import AI analysis results (JSON array of problems with measures) from chat export."""
    import time as _time
    problems = data.get("problems")
    if not isinstance(problems, list):
        return {"status": "error", "message": "Erwartet: {\"problems\": [...]}"}

    required = {"title", "description", "severity"}
    run_id = int(_time.time())
    count = 0
    for prob in problems:
        if not isinstance(prob, dict) or not required.issubset(prob.keys()):
            continue
        p = AiProblem(
            run_id=run_id,
            title=prob["title"],
            description=prob["description"],
            severity=prob.get("severity", "info"),
            category=prob.get("category"),
            status="pending",
        )
        db.add(p)
        db.flush()
        for m in prob.get("measures", []):
            if isinstance(m, dict) and "title" in m and "description" in m:
                mobj = AiMeasure(
                    problem_id=p.id,
                    title=m["title"],
                    description=m["description"],
                    status="pending",
                )
                db.add(mobj)
                db.flush()
                ai_c = (m.get("ai_comment") or "").strip()
                if ai_c:
                    db.add(AiComment(parent_type="measure", parent_id=mobj.id,
                                     text=ai_c, is_new=True))
        ai_c = (prob.get("ai_comment") or "").strip()
        if ai_c:
            db.add(AiComment(parent_type="problem", parent_id=p.id,
                             text=ai_c, is_new=True))
        count += 1
    db.commit()
    return {"status": "ok", "count": count}


@app.post("/api/ai/problems")
def api_create_problem(data: dict, db: Session = Depends(get_db)):
    """Manually create a problem."""
    import time as _time
    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    if not title or not description:
        return {"status": "error", "message": "Titel und Beschreibung sind Pflichtfelder"}
    severity = data.get("severity", "info")
    if severity not in ("info", "warning", "critical"):
        severity = "info"
    category = data.get("category") or None
    p = AiProblem(
        run_id=int(_time.time()),
        title=title,
        description=description,
        severity=severity,
        category=category,
        status="pending",
    )
    db.add(p)
    db.commit()
    return {"status": "ok", "id": p.id}


@app.post("/api/ai/analyze")
def api_ai_analyze(db: Session = Depends(get_db)):
    from .ai_analyzer import run_analysis
    try:
        problems = run_analysis(db)
        return {"status": "ok", "count": len(problems)}
    except Exception as exc:
        logger.error("AI-Analyse fehlgeschlagen: %s", exc)
        return {"status": "error", "message": str(exc)}


@app.get("/api/ai/problems")
def api_get_problems(db: Session = Depends(get_db)):
    problems = (
        db.query(AiProblem)
        .order_by(AiProblem.run_id.desc(), AiProblem.id.asc())
        .all()
    )
    measures = db.query(AiMeasure).all()
    all_comments = db.query(AiComment).order_by(AiComment.created_at.asc()).all()

    measures_by_problem: dict[int, list] = {}
    for m in measures:
        measures_by_problem.setdefault(m.problem_id, []).append(m)

    comments_by_parent: dict[tuple, list] = {}
    for c in all_comments:
        comments_by_parent.setdefault((c.parent_type, c.parent_id), []).append(c)

    def serialise_comments(parent_type, parent_id):
        return [
            {"id": c.id, "text": c.text, "created_at": c.created_at.isoformat(),
             "is_new": bool(c.is_new)}
            for c in comments_by_parent.get((parent_type, parent_id), [])
        ]

    return [
        {
            "id":          p.id,
            "run_id":      p.run_id,
            "created_at":  p.created_at.isoformat(),
            "title":       p.title,
            "description": p.description,
            "severity":    p.severity,
            "category":    p.category,
            "status":      p.status,
            "comments":    serialise_comments("problem", p.id),
            "measures": [
                {
                    "id":          m.id,
                    "title":       m.title,
                    "description": m.description,
                    "status":      m.status,
                    "created_at":  m.created_at.isoformat(),
                    "comments":    serialise_comments("measure", m.id),
                }
                for m in measures_by_problem.get(p.id, [])
            ],
        }
        for p in problems
    ]


@app.get("/api/ai/problems/{problem_id}")
def api_get_problem(problem_id: int, db: Session = Depends(get_db)):
    p = db.query(AiProblem).filter(AiProblem.id == problem_id).first()
    if not p:
        return {"status": "error", "message": "Nicht gefunden"}
    measures = db.query(AiMeasure).filter(AiMeasure.problem_id == problem_id).all()
    all_comments = db.query(AiComment).order_by(AiComment.created_at.asc()).all()
    comments_by_parent: dict[tuple, list] = {}
    for c in all_comments:
        comments_by_parent.setdefault((c.parent_type, c.parent_id), []).append(c)

    def serialise_comments(parent_type, parent_id):
        return [
            {"id": c.id, "text": c.text, "created_at": c.created_at.isoformat(),
             "is_new": bool(c.is_new)}
            for c in comments_by_parent.get((parent_type, parent_id), [])
        ]

    return {
        "id":          p.id,
        "run_id":      p.run_id,
        "created_at":  p.created_at.isoformat(),
        "title":       p.title,
        "description": p.description,
        "severity":    p.severity,
        "category":    p.category,
        "status":      p.status,
        "comments":    serialise_comments("problem", p.id),
        "measures": [
            {
                "id":          m.id,
                "title":       m.title,
                "description": m.description,
                "status":      m.status,
                "created_at":  m.created_at.isoformat(),
                "comments":    serialise_comments("measure", m.id),
            }
            for m in measures
        ],
    }


_VALID_STATUSES = {"pending", "rejected", "success", "failed", "check"}


@app.patch("/api/ai/problems/{problem_id}")
def api_update_problem(problem_id: int, data: dict, db: Session = Depends(get_db)):
    p = db.query(AiProblem).filter(AiProblem.id == problem_id).first()
    if not p:
        return {"status": "error", "message": "Nicht gefunden"}
    if "status" in data:
        if data["status"] not in _VALID_STATUSES:
            return {"status": "error", "message": "Ungültiger Status"}
        p.status = data["status"]
    db.commit()
    return {"status": "ok"}


@app.patch("/api/ai/measures/{measure_id}")
def api_update_measure(measure_id: int, data: dict, db: Session = Depends(get_db)):
    m = db.query(AiMeasure).filter(AiMeasure.id == measure_id).first()
    if not m:
        return {"status": "error", "message": "Nicht gefunden"}
    if "status" in data:
        if data["status"] not in _VALID_STATUSES:
            return {"status": "error", "message": "Ungültiger Status"}
        m.status = data["status"]
    db.commit()
    return {"status": "ok"}


@app.post("/api/ai/problems/{problem_id}/comments")
def api_add_problem_comment(problem_id: int, data: dict, db: Session = Depends(get_db)):
    text = (data.get("text") or "").strip()
    if not text:
        return {"status": "error", "message": "Kommentar darf nicht leer sein"}
    if not db.query(AiProblem).filter(AiProblem.id == problem_id).first():
        return {"status": "error", "message": "Problem nicht gefunden"}
    db.add(AiComment(parent_type="problem", parent_id=problem_id, text=text))
    db.commit()
    return {"status": "ok"}


@app.post("/api/ai/measures/{measure_id}/comments")
def api_add_measure_comment(measure_id: int, data: dict, db: Session = Depends(get_db)):
    text = (data.get("text") or "").strip()
    if not text:
        return {"status": "error", "message": "Kommentar darf nicht leer sein"}
    if not db.query(AiMeasure).filter(AiMeasure.id == measure_id).first():
        return {"status": "error", "message": "Maßnahme nicht gefunden"}
    db.add(AiComment(parent_type="measure", parent_id=measure_id, text=text))
    db.commit()
    return {"status": "ok"}


@app.delete("/api/ai/comments/{comment_id}")
def api_delete_comment(comment_id: int, db: Session = Depends(get_db)):
    c = db.query(AiComment).filter(AiComment.id == comment_id).first()
    if not c:
        return {"status": "error", "message": "Nicht gefunden"}
    db.delete(c)
    db.commit()
    return {"status": "ok"}


@app.patch("/api/ai/comments/{comment_id}/read")
def api_mark_comment_read(comment_id: int, db: Session = Depends(get_db)):
    """Mark a KI-generated comment as read (clears is_new flag)."""
    c = db.query(AiComment).filter(AiComment.id == comment_id).first()
    if not c:
        return {"status": "error", "message": "Nicht gefunden"}
    c.is_new = False
    db.commit()
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Debug API
# ---------------------------------------------------------------------------


@app.get("/api/debug")
def api_debug():
    return run_connection_check()


@app.get("/api/debug/services")
def api_debug_services():
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
