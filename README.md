# FritzBox Viewer

Web-Anwendung zur Anzeige und KI-gestützten Analyse des Ereignisprotokolls einer **FritzBox**.

## Features

- Automatischer, konfigurierbarer Abruf des FritzBox-Ereignislogs (TR-064)
- Persistente Speicherung in SQLite (keine Duplikate)
- Dark-Theme-Oberfläche mit sortierbarer und filterbarer Logtabelle
- Kategorisierung der Einträge (Fehler, Warnung, Internet, WLAN, Telefon, Mobile, System, Sicherheit)
- KI-gestützte Analyse der Logs mit Anthropic Claude (identifiziert Probleme, schlägt Maßnahmen vor)
- Zweistufige Problemverwaltung: Probleme → Maßnahmen mit Status-Workflow
- Kommentarfunktion mit Markdown-Unterstützung
- Vollständiger Export (Logs + Probleme + Maßnahmen) für manuelle KI-Analyse im Browser
- Alle Einstellungen werden über die Admin-Oberfläche im Browser konfiguriert

## Voraussetzungen

- Python 3.11+
- Zugang zur FritzBox im lokalen Netz
- FritzBox-Benutzer mit Berechtigung für das Heimnetz (TR-064 muss aktiv sein)

## TR-064 auf der FritzBox aktivieren

1. FritzBox-Oberfläche öffnen: `http://fritz.box`
2. **Heimnetz → Netzwerk → Heimnetzfreigaben**
3. Haken bei **"Statusinformationen über UPnP übertragen"** setzen
4. Speichern

## Installation

```bash
# 1. Repository klonen / in das Verzeichnis wechseln
cd FritzBox-Viewer

# 2. Virtuelle Umgebung erstellen
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

# 3. Abhängigkeiten installieren
pip install -r requirements.txt
```

## Starten

```bash
python run.py
```

Die Anwendung ist danach unter **http://localhost:8000** erreichbar.

Optional: `python run.py --debug` für ausführliche Log-Ausgaben.

## Erstkonfiguration

Beim ersten Start wird die SQLite-Datenbank angelegt. Anschließend unter **http://localhost:8000/admin** die Verbindungsdaten zur FritzBox eintragen:

- **Host / IP-Adresse** der FritzBox (Standard: `fritz.box`)
- **Benutzername** und **Passwort**
- **Abrufintervall** in Sekunden

Für die KI-Analyse zusätzlich den **Anthropic API-Key** hinterlegen (erhältlich unter [console.anthropic.com](https://console.anthropic.com)).

Alle Einstellungen werden in der lokalen SQLite-Datenbank gespeichert — keine Konfigurationsdateien erforderlich.

## Testen ohne echte FritzBox

```bash
python tests/insert_demo_data.py
```

## Projektstruktur

```
FritzBox-Viewer/
├── app/
│   ├── main.py          # FastAPI-App + API-Endpunkte
│   ├── database.py      # SQLAlchemy-Setup (SQLite) + Migrationen
│   ├── models.py        # Datenbankmodelle
│   ├── config_store.py  # DB-backed Konfigurationsspeicher
│   ├── fritzbox.py      # FritzBox-Anbindung (TR-064)
│   ├── scheduler.py     # Hintergrund-Scheduler (APScheduler)
│   ├── ai_analyzer.py   # KI-Analyse mit Anthropic Claude
│   └── templates/
│       ├── index.html         # Hauptseite (Logs + Problemtabelle)
│       ├── problem_detail.html # Detailseite eines Problems
│       └── admin.html         # Konfigurationsseite
├── ANLEITUNG.html       # Ausführliche Bedienungsanleitung
├── run.py               # Einstiegspunkt
└── requirements.txt
```

## API-Endpunkte (Auswahl)

| Methode | Pfad                         | Beschreibung                              |
|---------|------------------------------|-------------------------------------------|
| GET     | `/`                          | Hauptseite                                |
| GET     | `/admin`                     | Konfigurationsseite                       |
| GET     | `/problems/{id}`             | Detailseite eines Problems                |
| GET     | `/api/logs`                  | Log-Einträge (JSON, filterbar)            |
| GET     | `/api/stats`                 | Statistiken und Fetch-Status              |
| POST    | `/api/fetch`                 | Manuellen Log-Abruf auslösen             |
| POST    | `/api/ai/analyze`            | KI-Analyse starten                        |
| GET     | `/api/ai/problems`           | Alle Probleme mit Maßnahmen              |
| PATCH   | `/api/ai/problems/{id}`      | Problem-Status / Kommentar setzen         |
| PATCH   | `/api/ai/measures/{id}`      | Maßnahmen-Status / Kommentar setzen       |
| GET     | `/api/export/logs`           | Log-Export als Textdatei                  |
| GET     | `/api/export/full`           | Vollexport (Logs + Probleme + Maßnahmen)  |
| POST    | `/api/admin/config`          | Konfiguration speichern                   |
