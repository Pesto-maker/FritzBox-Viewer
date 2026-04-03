"""
Insert demo log entries for UI testing without a real FritzBox.
Run from project root:  python tests/insert_demo_data.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timedelta
import random

from app.database import engine, SessionLocal
from app.models import Base, LogEntry, FetchStatus

Base.metadata.create_all(bind=engine)

DEMO_ENTRIES = [
    ("internet", "Internetverbindung wurde erfolgreich hergestellt."),
    ("internet", "PPPoE-Verbindung getrennt, Neuverbindung wird gestartet."),
    ("internet", "DSL ist verfügbar (VDSL2, Profil 17a)."),
    ("internet", "Internetverbindung wurde getrennt."),
    ("wifi",     "WLAN-Gerät 'iPhone von Max' hat sich verbunden (2,4 GHz)."),
    ("wifi",     "WLAN-Gerät 'Laptop-Arbeit' hat sich verbunden (5 GHz)."),
    ("wifi",     "WLAN-Gerät 'SmartTV' getrennt."),
    ("wifi",     "WLAN-Netzwerk 'Heimnetz' neu gestartet."),
    ("phone",    "Eingehender Anruf von +4930123456 auf Rufnummer 12345."),
    ("phone",    "Ausgehender Anruf zu +4989987654 von Rufnummer 12345."),
    ("phone",    "SIP-Registrierung für Rufnummer 12345 erfolgreich."),
    ("error",    "Fehler: DSL-Verbindung konnte nicht hergestellt werden."),
    ("error",    "Fehler bei der Anmeldung am SIP-Server (Authentifizierung fehlgeschlagen)."),
    ("warning",  "Warnung: Speicherauslastung über 80 %."),
    ("system",   "Firmware-Update auf Version 07.57 erfolgreich installiert."),
    ("system",   "FritzBox wurde neu gestartet."),
    ("system",   "Automatisches Update aktiviert."),
    ("mobile",   "5G-Verbindung als Backup aktiv (Signal: -85 dBm)."),
    ("mobile",   "LTE-Backup deaktiviert, Festnetz wieder verfügbar."),
    ("security", "Portscanangriff von 203.0.113.42 erkannt und geblockt."),
    ("security", "Firewall: Verbindungsversuch auf Port 22 von 198.51.100.7 blockiert."),
    ("info",     "NAS-Gerät 'Synology DS923+' wurde erkannt."),
    ("info",     "Gastnetzzugang wurde aktiviert."),
    ("info",     "USB-Speicher 'SanDisk 64GB' wurde angeschlossen."),
]

db = SessionLocal()
now = datetime.now()

count = 0
for i in range(200):
    cat, msg = random.choice(DEMO_ENTRIES)
    ts = now - timedelta(minutes=random.randint(0, 60 * 24 * 30))
    exists = db.query(LogEntry).filter(
        LogEntry.timestamp == ts, LogEntry.message == msg
    ).first()
    if not exists:
        db.add(LogEntry(timestamp=ts, message=msg, category=cat))
        count += 1

status = db.query(FetchStatus).filter(FetchStatus.id == 1).first()
if not status:
    status = FetchStatus(id=1)
    db.add(status)
status.last_fetch = now
status.last_error = None
status.total_fetched = count

db.commit()
db.close()
print(f"Done — {count} demo entries inserted.")
