"""
FritzBox log fetcher.

Authentication strategy (in order):
  1. TR-064 GetDeviceLog       — works only if the user has "Fritz!Box-Einstellungen" permission
  2. TR-064 CreateUrlSID       — uses the already-working TR-064 Digest auth to obtain a
                                  web-session SID, then calls /api/v0/dino/eventlog via HTTPS.
                                  This avoids any PBKDF2 implementation entirely.

The PBKDF2 HTTP-login approach has been disabled: AVM's exact algorithm for
FritzOS 8.x (5-part challenge) is not publicly documented and repeated wrong
attempts lock the account.
"""

import os
import re
import logging
import socket
from datetime import datetime

import requests

from . import config_store

logger = logging.getLogger(__name__)


# FritzBox "group" field (from /api/v0/dino/eventlog) → internal category
_FRITZ_GROUP: dict[str, str] = {
    "sys":       "system",
    "wlan":      "wifi",
    "internet":  "internet",
    "dsl":       "internet",
    "telefonie": "phone",
    "usb":       "mobile",
    "firewall":  "security",
    "netz":      "info",
    "net":       "info",
}


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_fritzbox_logs() -> list[dict]:
    """Fetch the FritzBox event log and return a list of parsed entries."""
    host     = config_store.get("fritz_host")
    user     = config_store.get("fritz_user")
    password = config_store.get("fritz_password")

    logger.info("=== FritzBox Log Fetch START === host=%s user='%s'", host, user)

    # Method 1: TR-064 GetDeviceLog (requires "Fritz!Box-Einstellungen" permission)
    try:
        entries = _fetch_via_tr064_getlog(host, user, password)
        if entries:
            logger.info("Methode 1 (TR-064 GetDeviceLog): %d Einträge.", len(entries))
            return entries
        logger.warning(
            "TR-064 GetDeviceLog lieferte 0 Einträge — "
            "fehlende Berechtigung 'Fritz!Box-Einstellungen'? Versuche Methode 2…"
        )
    except Exception as exc:
        logger.warning("Methode 1 fehlgeschlagen: %s — versuche Methode 2…", exc)

    # Method 2: TR-064 CreateUrlSID → HTTPS eventlog REST API
    try:
        sid = _get_sid_via_tr064(host, user, password)
        entries = _fetch_eventlog_api(host, sid)
        logger.info("Methode 2 (TR-064-SID + eventlog-API): %d Einträge.", len(entries))
        return entries
    except Exception as exc:
        logger.warning("Methode 2 fehlgeschlagen: %s — versuche Methode 3…", exc)

    # Method 3: Manual SID from admin page
    manual_sid = config_store.get("manual_sid")
    if manual_sid:
        logger.info("Versuche manuell hinterlegte SID: %s…", manual_sid[:8])
        try:
            entries = _fetch_eventlog_api(host, manual_sid)
            logger.info("Manueller SID + eventlog-API: %d Einträge.", len(entries))
            return entries
        except Exception as exc:
            logger.warning("Manueller SID fehlgeschlagen (%s).", exc)

    raise RuntimeError(
        "Alle Authentifizierungsmethoden fehlgeschlagen. "
        "Bitte SID manuell in der Admin-Seite eintragen: http://localhost:8000/admin"
    )


def run_connection_check() -> dict:
    """
    Step-by-step connection diagnostics.
    Called by GET /api/debug — safe to call repeatedly (no login attempts).
    """
    from fritzconnection.core.fritzconnection import FritzConnection

    host     = config_store.get("fritz_host")
    user     = config_store.get("fritz_user")
    password = config_store.get("fritz_password")

    result: dict = {
        "config": {
            "host": host,
            "user": user or "(leer)",
            "password_set": bool(password),
        },
        "dns":              {"ok": False, "resolved_ip": None, "error": None},
        "tcp_49000":        {"ok": False, "error": None},
        "tr064_connect":    {"ok": False, "model": None, "firmware": None, "error": None},
        "tr064_getlog":     {"ok": False, "log_length": 0, "entries_parsed": 0,
                             "note": None, "error": None},
        "tr064_create_sid": {"ok": False, "sid_prefix": None, "error": None},
        "eventlog_api":     {"ok": False, "entries": 0, "first_msg": None, "error": None},
    }

    # ── DNS ──────────────────────────────────────────────────────────────────
    try:
        result["dns"]["resolved_ip"] = socket.gethostbyname(host)
        result["dns"]["ok"] = True
    except socket.gaierror as exc:
        result["dns"]["error"] = str(exc)
        return result

    # ── TCP port 49000 (TR-064) ───────────────────────────────────────────────
    try:
        s = socket.create_connection((host, 49000), timeout=5)
        s.close()
        result["tcp_49000"]["ok"] = True
    except OSError as exc:
        result["tcp_49000"]["error"] = str(exc)

    # ── TR-064 connect ────────────────────────────────────────────────────────
    fc = None
    try:
        fc = FritzConnection(address=host, user=user, password=password, timeout=10)
        result["tr064_connect"]["ok"]       = True
        result["tr064_connect"]["model"]    = getattr(fc, "modelname", "unbekannt")
        result["tr064_connect"]["firmware"] = getattr(fc, "system_version", "unbekannt")
    except Exception as exc:
        result["tr064_connect"]["error"] = str(exc)
        return result

    # ── TR-064 GetDeviceLog ───────────────────────────────────────────────────
    try:
        raw      = fc.call_action("DeviceInfo1", "GetDeviceLog")
        log_text = raw.get("NewDeviceLog", "")
        parsed   = [l for l in log_text.splitlines() if _parse_tr064_line(l)]
        result["tr064_getlog"]["ok"]            = True
        result["tr064_getlog"]["log_length"]    = len(log_text)
        result["tr064_getlog"]["entries_parsed"]= len(parsed)
        if not log_text:
            result["tr064_getlog"]["note"] = (
                "Leerer Log — Benutzer braucht Berechtigung 'Fritz!Box-Einstellungen': "
                "Fritz!Box-UI → System → Fritz!Box-Benutzer → Benutzer bearbeiten."
            )
    except Exception as exc:
        result["tr064_getlog"]["error"] = str(exc)

    # ── TR-064 CreateUrlSID ───────────────────────────────────────────────────
    sid = None
    try:
        sid = _get_sid_via_tr064(host, user, password)
        result["tr064_create_sid"]["ok"]         = True
        result["tr064_create_sid"]["sid_prefix"] = sid[:8] + "…"
    except Exception as exc:
        result["tr064_create_sid"]["error"] = str(exc)
        return result

    # ── eventlog REST API ─────────────────────────────────────────────────────
    try:
        entries = _fetch_eventlog_api(host, sid)
        result["eventlog_api"]["ok"]        = True
        result["eventlog_api"]["entries"]   = len(entries)
        result["eventlog_api"]["first_msg"] = entries[0]["message"] if entries else None
    except Exception as exc:
        result["eventlog_api"]["error"] = str(exc)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Method 1 — TR-064 GetDeviceLog
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_via_tr064_getlog(host: str, user: str, password: str) -> list[dict]:
    from fritzconnection.core.fritzconnection import FritzConnection

    fc = FritzConnection(address=host, user=user, password=password, timeout=10)
    logger.info("TR-064 verbunden: Modell=%s Firmware=%s",
                getattr(fc, "modelname", "?"), getattr(fc, "system_version", "?"))

    raw      = fc.call_action("DeviceInfo1", "GetDeviceLog")
    log_text = raw.get("NewDeviceLog", "")
    logger.info("TR-064 GetDeviceLog: %d Zeichen empfangen.", len(log_text))

    entries = [e for line in log_text.splitlines() if (e := _parse_tr064_line(line))]
    return entries


def _parse_tr064_line(line: str) -> dict | None:
    """Parse a TR-064 log line: 'DD.MM.YY HH:MM:SS Message'"""
    line = line.strip()
    if not line:
        return None
    m = re.match(r"^(\d{2}\.\d{2}\.\d{2})\s+(\d{2}:\d{2}:\d{2})\s+(.+)$", line)
    if not m:
        return None
    date_str, time_str, message = m.groups()
    try:
        timestamp = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M:%S")
    except ValueError:
        return None
    return {"timestamp": timestamp, "message": message.strip(),
            "category": _detect_category(message)}


# ─────────────────────────────────────────────────────────────────────────────
# Method 2 — TR-064 CreateUrlSID + HTTPS eventlog API
# ─────────────────────────────────────────────────────────────────────────────

def _get_sid_via_tr064(host: str, user: str, password: str) -> str:
    """
    Call TR-064 action X_AVM-DE_Auth1/X_AVM-DE_CreateUrlSID to get a
    web-session SID. TR-064 uses HTTP Digest auth which already works —
    no PBKDF2 needed.
    """
    from fritzconnection.core.fritzconnection import FritzConnection

    fc     = FritzConnection(address=host, user=user, password=password, timeout=10)
    result = fc.call_action("DeviceConfig1", "X_AVM-DE_CreateUrlSID")
    url_sid: str = result.get("NewX_AVM-DE_UrlSID", "")
    logger.info("X_AVM-DE_CreateUrlSID → %r", url_sid)

    # url_sid is typically "?sid=abcdef1234567890"
    sid = url_sid.split("sid=")[-1].strip("& ") if "sid=" in url_sid else url_sid.strip()

    if not sid or sid == "0000000000000000":
        raise RuntimeError(
            f"X_AVM-DE_CreateUrlSID lieferte ungültige SID: {url_sid!r}. "
            "Möglicherweise fehlt dem Benutzer die Berechtigung 'Smart Home' oder "
            "'Fritz!Box-Einstellungen'."
        )

    logger.info("SID erhalten: %s…", sid[:8])
    return sid


def _fetch_eventlog_api(host: str, sid: str) -> list[dict]:
    """
    GET https://<host>/api/v0/dino/eventlog?sid=<sid>
    Returns list of dicts: {timestamp, message, category}
    """
    url = f"https://{host}/api/v0/dino/eventlog"
    headers = {
        "Authorization": f"AVM-SID {sid}",
        "Accept": "*/*",
    }
    r = requests.get(url, headers=headers, timeout=10, verify=False)
    if not r.ok:
        body = r.text[:500] if r.text else "(no body)"
        logger.warning("eventlog-API HTTP %d: %s", r.status_code, body)
    r.raise_for_status()

    raw = r.json()
    if not isinstance(raw, list):
        raise ValueError(
            f"Unerwartetes Antwortformat von eventlog-API: "
            f"{type(raw).__name__}: {str(raw)[:300]}"
        )

    logger.info("eventlog-API: %d Roh-Einträge empfangen.", len(raw))
    return _parse_eventlog_rows(raw)


def _parse_eventlog_rows(rows: list) -> list[dict]:
    """
    Parse rows from /api/v0/dino/eventlog.
    Row format: {"date": "03.04.26", "time": "09:33:34", "msg": "…", "group": "sys", "id": 501}
    """
    entries, skipped = [], 0
    for row in rows:
        try:
            if isinstance(row, dict):
                date_str = row["date"]
                time_str = row["time"]
                message  = row["msg"]
                group    = row.get("group", "")
            elif isinstance(row, (list, tuple)) and len(row) >= 3:
                date_str, time_str, message = str(row[0]), str(row[1]), str(row[2])
                group = str(row[4]) if len(row) > 4 else ""
            else:
                skipped += 1
                continue

            timestamp = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%y %H:%M:%S")
            category  = _FRITZ_GROUP.get(group) or _detect_category(message)
            entries.append({"timestamp": timestamp, "message": message, "category": category})
        except Exception as exc:
            logger.debug("Zeile übersprungen: %r (%s)", row, exc)
            skipped += 1

    logger.info("Geparst: %d Einträge, %d übersprungen.", len(entries), skipped)
    return entries


# ─────────────────────────────────────────────────────────────────────────────
# Category detection (fallback when "group" is unknown)
# ─────────────────────────────────────────────────────────────────────────────

def _detect_category(message: str) -> str:
    msg = message.lower()
    if any(w in msg for w in ["fehler", "error", "fail", "ungültig", "invalid"]):
        return "error"
    if any(w in msg for w in ["warnung", "warning"]):
        return "warning"
    if any(w in msg for w in ["internet", "dsl", "online", "verbunden", "connected",
                               "eingewählt", "sync"]):
        return "internet"
    if any(w in msg for w in ["wlan", "wifi", "wireless", "802.11"]):
        return "wifi"
    if any(w in msg for w in ["telefon", "phone", "anruf", "call", "sip", "fax",
                               "rufnummer"]):
        return "phone"
    if any(w in msg for w in ["5g", "lte", "mobilfunk", "mobile", "usb", "sim"]):
        return "mobile"
    if any(w in msg for w in ["update", "firmware", "neustart", "reboot", "start"]):
        return "system"
    if any(w in msg for w in ["firewall", "block", "geblockt", "attack", "angriff",
                               "port scan", "portscan"]):
        return "security"
    return "info"
