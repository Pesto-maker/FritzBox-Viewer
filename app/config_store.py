"""
DB-backed configuration store.
Priority: DB value → .env / environment variable → default
Secrets (fritz_password, anthropic_api_key) are stored Fernet-encrypted.
"""
import os
from .crypto import SECRET_KEYS, decrypt, encrypt
from .database import SessionLocal
from .models import AppConfig

DEFAULT_SYSTEM_PROMPT_LOGS = """\
Du bist ein Netzwerk- und Sicherheitsexperte für Heimnetzwerke.

Ich lade dir nachfolgend einen Export der FritzBox-Ereignisprotokolle hoch.
Der Export enthält Logeinträge mit Zeitstempel und Kategorie.

Bitte analysiere die Daten und:
1. Identifiziere Auffälligkeiten, Fehler und mögliche Sicherheitsrisiken.
2. Priorisiere deine Empfehlungen (kritisch zuerst).
3. Gib für jedes identifizierte Problem 1–3 konkrete, umsetzbare Maßnahmen an.
4. Beschränke dich auf tatsächliche Auffälligkeiten — keine generischen Sicherheitstipps.
5. Beschreibungen und Kommentare können Markdown-Formatierung verwenden (Listen, Fettdruck, Code-Blöcke etc.), sofern das die Lesbarkeit verbessert.

WICHTIG — Ausgabeformat:
Antworte ausschließlich mit einem JSON-Array ohne Markdown-Blöcke oder Erklärungen,
damit deine Antwort direkt in den FritzBox Viewer importiert werden kann:
[
  {
    "title": "Kurzer Problemtitel (max. 80 Zeichen)",
    "description": "Detaillierte Problembeschreibung.",
    "severity": "critical",
    "category": "security",
    "measures": [
      {
        "title": "Maßnahme 1 (max. 80 Zeichen)",
        "description": "Konkrete Umsetzungsschritte.",
        "ai_comment": "Optional: KI-Anmerkung zu dieser Maßnahme"
      }
    ],
    "ai_comment": "Optional: KI-Anmerkung zu diesem Problem"
  }
]
Erlaubte severity-Werte: critical | warning | info
Erlaubte category-Werte: internet | wifi | phone | security | system | mobile | info"""

DEFAULT_SYSTEM_PROMPT_FULL = """\
Du bist ein Netzwerk- und Sicherheitsexperte für Heimnetzwerke.

Ich lade dir nachfolgend einen vollständigen Export aus dem FritzBox Viewer hoch.
Der Export enthält:
- FritzBox-Ereignisprotokolle mit Zeitstempel und Kategorie
- Identifizierte Probleme mit ihrem aktuellen Bearbeitungsstatus
- Zugehörige Maßnahmen mit Status (offen / in Prüfung / abgelehnt / erfolgreich / nicht erfolgreich) und Kommentaren des Betreibers

Bitte analysiere die Daten und beachte folgende Regeln:
1. Probleme mit Status "erfolgreich": Keine neuen Maßnahmen — du kannst jedoch einen ai_comment mit einer abschließenden Anmerkung hinterlassen.
2. Probleme mit Status "nicht erfolgreich" oder "in Prüfung": Schlage alternative oder ergänzende Maßnahmen vor, berücksichtige dabei die Kommentare des Betreibers.
3. Abgelehnte Probleme: Respektiere die Entscheidung — du kannst einen ai_comment hinterlassen, sofern kein kritisches Sicherheitsrisiko besteht.
4. Neue Maßnahmen werden NUR für Probleme mit Status "offen" oder "in Prüfung" erstellt.
5. Identifiziere neue Auffälligkeiten in den Logs, die noch nicht als Problem erfasst sind.
6. Priorisiere deine Empfehlungen (kritisch zuerst).
7. Beschreibungen und Kommentare können Markdown-Formatierung verwenden (Listen, Fettdruck, Code-Blöcke etc.), sofern das die Lesbarkeit verbessert.

WICHTIG — Ausgabeformat:
Antworte ausschließlich mit einem JSON-Array ohne Markdown-Blöcke oder Erklärungen,
damit deine Antwort direkt in den FritzBox Viewer importiert werden kann:
[
  {
    "title": "Kurzer Problemtitel (max. 80 Zeichen)",
    "description": "Detaillierte Problembeschreibung.",
    "severity": "critical|warning|info",
    "category": "internet|wifi|phone|security|system|mobile|info",
    "measures": [
      {
        "title": "Maßnahme 1 (max. 80 Zeichen)",
        "description": "Konkrete Umsetzungsschritte.",
        "ai_comment": "Optional: KI-Anmerkung zu dieser Maßnahme"
      }
    ],
    "ai_comment": "Optional: KI-Anmerkung zu diesem Problem (für alle Status-Typen möglich)"
  }
]
Erlaubte severity-Werte: critical | warning | info
Erlaubte category-Werte: internet | wifi | phone | security | system | mobile | info"""

_DEFAULTS = {
    "fritz_host":           ("FRITZ_HOST",         "fritz.box"),
    "fritz_user":           ("FRITZ_USER",         ""),
    "fritz_password":       ("FRITZ_PASSWORD",     ""),
    "fetch_interval":       ("FETCH_INTERVAL",     "300"),
    "manual_sid":           (None,                 ""),
    "anthropic_api_key":    ("ANTHROPIC_API_KEY",  ""),
    "system_prompt_logs":   (None, DEFAULT_SYSTEM_PROMPT_LOGS),
    "system_prompt_full":   (None, DEFAULT_SYSTEM_PROMPT_FULL),
}


def get(key: str) -> str:
    db = SessionLocal()
    try:
        row = db.query(AppConfig).filter(AppConfig.key == key).first()
        if row and row.value is not None:
            value = row.value
            if key in SECRET_KEYS:
                value = decrypt(value)
            return value
    finally:
        db.close()
    env_key, default = _DEFAULTS.get(key, (None, ""))
    if env_key:
        return os.getenv(env_key, default)
    return default


def set(key: str, value: str):
    stored = encrypt(value) if key in SECRET_KEYS and value else value
    db = SessionLocal()
    try:
        row = db.query(AppConfig).filter(AppConfig.key == key).first()
        if row:
            row.value = stored
        else:
            db.add(AppConfig(key=key, value=stored))
        db.commit()
    finally:
        db.close()


def get_all_public() -> dict:
    """Return all config values (secrets masked)."""
    return {
        "fritz_host":           get("fritz_host"),
        "fritz_user":           get("fritz_user"),
        "fritz_password":       "••••••••" if get("fritz_password") else "",
        "fetch_interval":       get("fetch_interval"),
        "manual_sid":           get("manual_sid"),
        "anthropic_api_key":    "••••••••" if get("anthropic_api_key") else "",
        "system_prompt_logs":   get("system_prompt_logs"),
        "system_prompt_full":   get("system_prompt_full"),
    }
