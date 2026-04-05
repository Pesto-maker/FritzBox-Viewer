# FritzBox Viewer

Web-Anwendung zur Anzeige und KI-gestützten Analyse des Ereignisprotokolls einer **FritzBox** (kompatibel mit allen Modellen, die TR-064 unterstützen).

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

## Analysevarianten

Der FritzBox Viewer unterstützt drei Wege, um aus den Logs Probleme und Maßnahmen zu erarbeiten. Die Varianten lassen sich auch kombinieren.

### 1. Export + manuelle KI-Analyse (kein API-Key erforderlich)

Die gesammelten Logs sowie alle bereits erfassten Probleme und Maßnahmen lassen sich als strukturierte Textdatei exportieren. Diese Datei kann in einen beliebigen KI-Chat (z. B. Claude.ai, ChatGPT) hochgeladen werden.

- **Logs exportieren** — enthält nur die Rohlogs; geeignet für eine Erstanalyse
- **Vollständig exportieren** — enthält Logs, Probleme, Maßnahmen und deren Status; ideal für Folgeanalysen, da die KI bereits bearbeitete Themen berücksichtigen kann

Jeder Export-Button zeigt auf Wunsch den passenden **Systemprompt** an, der der KI erklärt, wie sie die Daten interpretieren und in welchem Format sie antworten soll. KI-Antworten können anschließend per **"KI-Import"** direkt in den Viewer übernommen werden.

### 2. Direkte KI-Analyse über Anthropic API

Mit einem Anthropic API-Key wird die Analyse vollständig im Viewer durchgeführt — kein manueller Export nötig.

- API-Key unter **Admin → KI-Einstellungen** hinterlegen
- Auf der Hauptseite **"KI-Analyse starten"** klicken
- Probleme und Maßnahmen erscheinen automatisch in der Tabelle

Der Systemprompt ist über die Admin-Seite anpassbar. Folgeanalysen berücksichtigen automatisch bereits bearbeitete, abgelehnte oder erfolgreich umgesetzte Probleme.

### 3. Manuelle Erfassung

Probleme und Maßnahmen können vollständig ohne KI-Beteiligung erfasst werden.

- In der Problemtabelle auf **"Neu"** klicken
- Titel, Beschreibung, Schweregrad und Kategorie eingeben
- Maßnahmen direkt auf der Detailseite des Problems ergänzen

Dies ist nützlich, wenn Auffälligkeiten beim Durchsehen der Logs manuell festgestellt werden oder wenn keine KI-Anbindung gewünscht ist.

---

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
