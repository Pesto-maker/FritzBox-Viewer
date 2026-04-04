"""
AI-powered FritzBox log analysis using the Anthropic API.

Sends recent log entries plus the full history of previous problems and measures
(with their status and comments) so the model can avoid repeating already-handled
issues and focus on new findings.
"""

import json
import logging
import time

import anthropic

from . import config_store
from .models import AiProblem, AiMeasure, AiComment, LogEntry

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_LOGS = 400


def run_analysis(db) -> list[dict]:
    """
    Fetch logs + previous problems/measures, call Claude, persist results.
    Returns the list of new problem dicts (each with a 'measures' list).
    """
    api_key = config_store.get("anthropic_api_key")
    if not api_key:
        raise ValueError(
            "Kein Anthropic API-Key konfiguriert. "
            "Bitte unter Admin → KI-Einstellungen eintragen."
        )

    logs = (
        db.query(LogEntry)
        .order_by(LogEntry.timestamp.desc())
        .limit(MAX_LOGS)
        .all()
    )
    if not logs:
        raise ValueError("Keine Logeinträge vorhanden — bitte zuerst Logs abrufen.")
    logs = list(reversed(logs))  # chronological order

    prev_problems = (
        db.query(AiProblem)
        .order_by(AiProblem.created_at.desc())
        .all()
    )
    prev_measures = db.query(AiMeasure).all()
    all_comments  = db.query(AiComment).order_by(AiComment.created_at.asc()).all()

    measures_by_problem: dict[int, list] = {}
    for m in prev_measures:
        measures_by_problem.setdefault(m.problem_id, []).append(m)

    comments_by_parent: dict[tuple, list] = {}
    for c in all_comments:
        comments_by_parent.setdefault((c.parent_type, c.parent_id), []).append(c)

    prompt = _build_prompt(logs, prev_problems, measures_by_problem, comments_by_parent)
    logger.info(
        "AI-Analyse: %d Logeinträge, %d frühere Probleme.",
        len(logs), len(prev_problems),
    )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    logger.info("AI-Antwort erhalten, %d Zeichen.", len(raw))

    problems = _parse_response(raw)

    run_id = int(time.time())
    for prob in problems:
        p = AiProblem(
            run_id=run_id,
            title=prob["title"],
            description=prob["description"],
            severity=prob.get("severity", "info"),
            category=prob.get("category"),
            status="pending",
        )
        db.add(p)
        db.flush()  # p.id is now available
        for m in prob.get("measures", []):
            db.add(AiMeasure(
                problem_id=p.id,
                title=m["title"],
                description=m["description"],
                status="pending",
            ))
    db.commit()
    logger.info(
        "AI-Analyse: %d neue Probleme gespeichert (run_id=%d).",
        len(problems), run_id,
    )
    return problems


# ─────────────────────────────────────────────────────────────────────────────
# Prompt builder
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_comments(parent_type: str, parent_id: int, comments_by_parent: dict, indent: str) -> str:
    clist = comments_by_parent.get((parent_type, parent_id), [])
    if not clist:
        return ""
    lines = []
    for c in clist:
        ts = c.created_at.strftime("%d.%m.%y %H:%M")
        lines.append(f'{indent}[{ts}] {c.text}')
    return "\n" + "\n".join(lines)


def _build_prompt(logs: list, prev_problems: list, measures_by_problem: dict,
                  comments_by_parent: dict) -> str:
    log_lines = "\n".join(
        f"{e.timestamp.strftime('%d.%m.%y %H:%M:%S')} [{e.category}] {e.message}"
        for e in logs
    )

    prev_section = ""
    if prev_problems:
        success  = [p for p in prev_problems if p.status == "success"]
        failed   = [p for p in prev_problems if p.status in ("failed", "check")]
        rejected = [p for p in prev_problems if p.status == "rejected"]
        pending  = [p for p in prev_problems if p.status == "pending"]

        prev_section = "\n\n## Bisherige Probleme und Maßnahmen\n"

        def fmt_problem(p):
            out = f"- {p.title}"
            out += _fmt_comments("problem", p.id, comments_by_parent, "    ")
            for m in measures_by_problem.get(p.id, []):
                out += f"\n  → Maßnahme ({m.status}): {m.title}"
                out += _fmt_comments("measure", m.id, comments_by_parent, "      ")
            return out

        if success:
            prev_section += "\n**Erfolgreich umgesetzt — nicht erneut empfehlen:**\n"
            prev_section += "\n".join(fmt_problem(p) for p in success) + "\n"

        if failed:
            prev_section += "\n**Umgesetzt aber nicht erfolgreich — alternative Maßnahmen vorschlagen:**\n"
            prev_section += "\n".join(fmt_problem(p) for p in failed) + "\n"

        if rejected:
            prev_section += "\n**Abgelehnt — nur bei kritischem Sicherheitsrisiko erneut empfehlen:**\n"
            prev_section += "\n".join(fmt_problem(p) for p in rejected) + "\n"

        if pending:
            prev_section += "\n**Noch offen:**\n"
            prev_section += "\n".join(fmt_problem(p) for p in pending) + "\n"

    return f"""Du bist ein Netzwerk- und Sicherheitsexperte und analysierst FritzBox-Ereignisprotokolle für einen Heimnetzwerk-Betreiber.

## Aufgabe
Analysiere die Logeinträge und erstelle konkrete, umsetzbare Empfehlungen.
Fokussiere dich auf tatsächliche Auffälligkeiten — keine generischen Sicherheitstipps.{prev_section}

## Logeinträge ({len(logs)} Einträge, chronologisch)
{log_lines}

## Antwortformat
Antworte AUSSCHLIESSLICH mit einem JSON-Array, ohne Markdown-Blöcke oder sonstige Erklärungen:
[
  {{
    "title": "Kurzer prägnanter Titel des Problems (max. 80 Zeichen)",
    "description": "Detaillierte Beschreibung des identifizierten Problems.",
    "severity": "info|warning|critical",
    "category": "internet|wifi|phone|security|system|mobile|info",
    "measures": [
      {{
        "title": "Maßnahme 1 (max. 80 Zeichen)",
        "description": "Konkrete Umsetzungsschritte für den Betreiber."
      }},
      {{
        "title": "Maßnahme 2 (max. 80 Zeichen)",
        "description": "Alternative oder ergänzende Maßnahme."
      }}
    ]
  }}
]

Erstelle 3–7 priorisierte Probleme (critical zuerst), jeweils mit 1–3 Maßnahmen.
Wenn keine relevanten Auffälligkeiten vorhanden sind, gib ein leeres Array zurück."""


# ─────────────────────────────────────────────────────────────────────────────
# Response parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_response(raw: str) -> list[dict]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"Unerwartetes Antwortformat: {type(data).__name__}")

    required = {"title", "description", "severity"}
    valid = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if not required.issubset(item.keys()):
            logger.warning("Problem übersprungen (fehlende Felder): %r", item)
            continue
        # Validate measures list
        measures = []
        for m in item.get("measures", []):
            if isinstance(m, dict) and "title" in m and "description" in m:
                measures.append(m)
            else:
                logger.warning("Maßnahme übersprungen (fehlende Felder): %r", m)
        item["measures"] = measures
        valid.append(item)

    return valid
