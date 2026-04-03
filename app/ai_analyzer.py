"""
AI-powered FritzBox log analysis using the Anthropic API.

Sends recent log entries plus the history of previous recommendations
(with their accepted/rejected status) so the model can avoid repeating
already-handled issues and focus on new findings.
"""

import json
import logging
import time

import anthropic

from . import config_store
from .models import AiRecommendation, LogEntry

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-4-6"
MAX_LOGS = 400  # entries sent to the model


def run_analysis(db) -> list[dict]:
    """
    Fetch logs + previous recommendations, call Claude, persist results.
    Returns the list of new recommendation dicts.
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

    prev_recs = (
        db.query(AiRecommendation)
        .order_by(AiRecommendation.created_at.desc())
        .all()
    )

    prompt = _build_prompt(logs, prev_recs)
    logger.info("AI-Analyse: %d Logeinträge, %d frühere Empfehlungen.", len(logs), len(prev_recs))

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text
    logger.info("AI-Antwort erhalten, %d Zeichen.", len(raw))

    recommendations = _parse_response(raw)

    run_id = int(time.time())
    for rec in recommendations:
        db.add(AiRecommendation(
            run_id=run_id,
            title=rec["title"],
            description=rec["description"],
            severity=rec.get("severity", "info"),
            category=rec.get("category"),
            status="pending",
        ))
    db.commit()
    logger.info("AI-Analyse: %d neue Empfehlungen gespeichert (run_id=%d).", len(recommendations), run_id)
    return recommendations


# ─────────────────────────────────────────────────────────────────────────────
# Prompt builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_prompt(logs: list, prev_recs: list) -> str:
    log_lines = "\n".join(
        f"{e.timestamp.strftime('%d.%m.%y %H:%M:%S')} [{e.category}] {e.message}"
        for e in logs
    )

    prev_section = ""
    if prev_recs:
        accepted = [r for r in prev_recs if r.status == "accepted"]
        rejected = [r for r in prev_recs if r.status == "rejected"]
        pending  = [r for r in prev_recs if r.status == "pending"]

        prev_section = "\n\n## Frühere Empfehlungen\n"
        if accepted:
            prev_section += "\n**Bereits umgesetzt — nicht erneut empfehlen:**\n"
            for r in accepted:
                prev_section += f"- {r.title}\n"
        if rejected:
            prev_section += "\n**Abgelehnt — nur erneut empfehlen wenn kritisch:**\n"
            for r in rejected:
                prev_section += f"- {r.title}\n"
        if pending:
            prev_section += "\n**Noch offen (bekannt, trotzdem relevant falls neue Erkenntnisse):**\n"
            for r in pending:
                prev_section += f"- {r.title}\n"

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
    "title": "Kurzer prägnanter Titel (max. 80 Zeichen)",
    "description": "Detaillierte Beschreibung des Problems und konkrete Handlungsempfehlung für den Betreiber.",
    "severity": "info|warning|critical",
    "category": "internet|wifi|phone|security|system|mobile|info"
  }}
]

Erstelle 3–7 priorisierte Empfehlungen (critical zuerst). Wenn keine relevanten Auffälligkeiten vorhanden sind, gib ein leeres Array zurück."""


# ─────────────────────────────────────────────────────────────────────────────
# Response parser
# ─────────────────────────────────────────────────────────────────────────────

def _parse_response(raw: str) -> list[dict]:
    text = raw.strip()
    # Strip markdown code fences if the model added them anyway
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
            logger.warning("Empfehlung übersprungen (fehlende Felder): %r", item)
            continue
        valid.append(item)

    return valid
