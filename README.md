# FritzBox Viewer

Web-Anwendung zur Anzeige und Analyse des Ereignisprotokolls einer **FritzBox 6580 5G**.

## Features

- Automatischer, konfigurierbarer Abruf des FritzBox-Ereignislogs (TR-064)
- Persistente Speicherung in SQLite (keine Duplikate)
- Dark-Theme-Oberfläche mit sortierbarer und filterbarer Tabelle
- Kategorisierung der Einträge (Fehler, Warnung, Internet, WLAN, Telefon, Mobile, System, Sicherheit)
- Statistik-Übersicht und manueller Abruf per Knopfdruck

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

# 4. Konfiguration anlegen
cp .env.example .env
```

## Konfiguration (`.env`)

```dotenv
FRITZ_HOST=fritz.box          # IP oder Hostname der FritzBox
FRITZ_USER=                   # Benutzername (leer = Standard-Benutzer)
FRITZ_PASSWORD=your_password  # FritzBox-Passwort
FETCH_INTERVAL=300            # Abrufintervall in Sekunden (Standard: 5 min)
```

> **Hinweis:** Wenn an der FritzBox kein separater Benutzer eingerichtet ist,
> kann `FRITZ_USER` leer bleiben. Das Passwort ist dann das FritzBox-Zugangskennwort.

## Starten

```bash
python run.py
```

Die Anwendung ist danach unter **http://localhost:8000** erreichbar.

Beim ersten Start wird:
1. Die SQLite-Datenbank `fritzbox_logs.db` im aktuellen Verzeichnis angelegt.
2. Sofort ein erster Log-Abruf gestartet.
3. Der Scheduler aktiviert (Intervall laut `FETCH_INTERVAL`).

## Testen ohne echte FritzBox

Zum Testen der Oberfläche ohne FritzBox kann die API mit Demo-Daten befüllt werden:

```bash
# In einem separaten Terminal (venv aktiv):
python tests/insert_demo_data.py
```

## Projektstruktur

```
FritzBox-Viewer/
├── app/
│   ├── main.py          # FastAPI-App
│   ├── database.py      # SQLAlchemy-Setup (SQLite)
│   ├── models.py        # Datenbankmodelle
│   ├── fritzbox.py      # FritzBox-Anbindung (TR-064)
│   ├── scheduler.py     # Hintergrund-Scheduler (APScheduler)
│   └── templates/
│       └── index.html   # Frontend (Bootstrap 5 Dark + DataTables)
├── infrastructure/
│   └── synology/        # K3s-Deployment auf Synology NAS
├── run.py               # Einstiegspunkt
├── requirements.txt
└── .env.example
```

## API-Endpunkte

| Methode | Pfad          | Beschreibung                         |
|---------|---------------|--------------------------------------|
| GET     | `/`           | Web-Oberfläche                       |
| GET     | `/api/logs`   | Log-Einträge (JSON, filterbar)       |
| GET     | `/api/stats`  | Statistiken und Fetch-Status         |
| POST    | `/api/fetch`  | Manuellen Abruf auslösen            |

### `/api/logs` Parameter

| Parameter  | Typ    | Standard | Beschreibung                        |
|------------|--------|----------|-------------------------------------|
| `limit`    | int    | 500      | Max. Anzahl Einträge                |
| `offset`   | int    | 0        | Paginierung                         |
| `category` | string | —        | Filter nach Kategorie               |
| `search`   | string | —        | Volltextsuche in der Nachricht      |
| `sort_by`  | string | timestamp| Sortierfeld                         |
| `sort_dir` | string | desc     | `asc` oder `desc`                   |
