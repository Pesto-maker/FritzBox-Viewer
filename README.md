# FritzBox Viewer

Web-Anwendung zur Anzeige und KI-gestützten Analyse des Ereignisprotokolls einer **FritzBox** (kompatibel mit allen Modellen, die TR-064 unterstützen).

## Features

- Automatischer, konfigurierbarer Abruf des FritzBox-Ereignislogs (TR-064 + HTTPS-API)
- Persistente Speicherung in SQLite
- Dark-Theme-Oberfläche mit sortierbarer und filterbarer Logtabelle
- Kategorisierung der Einträge (Fehler, Warnung, Internet, WLAN, Telefon, Mobile, System, Sicherheit)
- KI-gestützte Analyse — direkt per API-Key oder über einen geführten Assistenten für jeden beliebigen Chat-KI-Dienst (ohne API-Key)
- Zweistufige Problemverwaltung: Probleme → Maßnahmen mit Status-Workflow
- Kommentarfunktion mit Markdown-Unterstützung
- Löschen von Problemen, Maßnahmen und Kommentaren

## Deployment

### Option A — Windows-Exe

ZIP entpacken und `FritzBox-Viewer.exe` starten.

**Selbst bauen** (einmalig, Python + venv muss installiert sein):
```
build.bat
```
Ausgabe: `dist/FritzBox-Viewer/FritzBox-Viewer.exe`

Die Datenbank (`fritzbox_logs.db`) wird beim ersten Start automatisch neben der Exe angelegt.

### Option B — Python direkt

```bash
python run.py
# oder mit ausführlicher Ausgabe:
python run.py --debug
```


## Voraussetzungen (Python-Variante)

- Python 3.11+
- Zugang zur FritzBox im lokalen Netz
- FritzBox-Benutzer mit Berechtigung für das Heimnetz (TR-064 muss aktiv sein)

## Verbindung zur FritzBox

Der Log-Abruf läuft in zwei Schritten:

1. **Authentifizierung via TR-064** — der Viewer ruft über das TR-064-Protokoll eine Session-ID (SID) ab; dazu muss TR-064 auf der FritzBox aktiv sein
2. **Log-Abruf via HTTPS-API** — mit der SID werden die Ereignisprotokolleinträge über `https://fritz.box/api/v0/dino/eventlog` abgerufen

Als Fallback wird auch `GetDeviceLog` direkt per TR-064 unterstützt (erfordert die Berechtigung "Fritz!Box-Einstellungen" für den FritzBox-Benutzer).

### TR-064 aktivieren

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

Beim ersten Start öffnet die App automatisch die **Admin-Seite** der Anwendung. Dort bitte die Verbindungsdaten zur FritzBox eintragen:

- **Host / IP-Adresse** der FritzBox (Standard: `fritz.box`)
- **Benutzername** und **Passwort**
- **Abrufintervall** in Sekunden (Default: 300)

## Analysevarianten

Der FritzBox Viewer unterstützt drei Wege, um aus den Logs Probleme und Maßnahmen zu erarbeiten. Die Varianten lassen sich auch kombinieren.

### 1. Direkte KI-Analyse (Anthropic API-Key hinterlegt)

Ist unter **Admin → KI-Einstellungen** ein Anthropic API-Key eingetragen, läuft die Analyse vollständig im Viewer.

- Auf der Hauptseite rechts **"KI-Analyse"** klicken
- Claude wertet die letzten Logeinträge plus den aktuellen Problemstatus aus
- Neue Probleme und Maßnahmen erscheinen automatisch in der Tabelle

Folgeanalysen referenzieren bereits existierende Probleme per ID, sodass keine Duplikate entstehen. Kommentare und Status (offen / in Prüfung / erfolgreich / nicht erfolgreich / abgelehnt) werden als Kontext mitgegeben.

### 2. Geführter Assistent für externe KI-Chats (kein API-Key)

Ohne API-Key öffnet ein Klick auf **"KI-Analyse"** einen **3-Schritt-Assistenten**:

1. **Kopieren** — der Assistent legt Systemprompt, Logs und bestehende Probleme in einem Textblock in der Zwischenablage ab. Bei sehr großen Exporten lässt sich die Log-Anzahl reduzieren
2. **Einfügen & Senden** — den Text in einen beliebigen KI-Chat (Mistral.ai, Claude.ai, ChatGPT, Gemini …) einfügen und abschicken
3. **Antwort importieren** — die JSON-Antwort der KI zurück in den Assistenten einfügen; der Viewer übernimmt neue Probleme und aktualisiert bestehende

Es werden keine Dateien heruntergeladen — alles läuft über die Zwischenablage.

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
├── ANLEITUNG.html           # Ausführliche Bedienungsanleitung
├── fritzbox_viewer.spec     # PyInstaller-Konfiguration
├── build.bat                # Build-Skript für Windows-Exe
├── run.py                   # Einstiegspunkt
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
| POST    | `/api/ai/analyze`            | Direkte KI-Analyse starten (benötigt API-Key) |
| POST    | `/api/ai/import`             | JSON-Antwort aus externem KI-Chat importieren |
| GET     | `/api/ai/problems`           | Alle Probleme mit Maßnahmen               |
| PATCH   | `/api/ai/problems/{id}`      | Problem-Status / Kommentar setzen         |
| DELETE  | `/api/ai/problems/{id}`      | Problem löschen (kaskadiert Maßnahmen + Kommentare) |
| PATCH   | `/api/ai/measures/{id}`      | Maßnahmen-Status / Kommentar setzen       |
| DELETE  | `/api/ai/measures/{id}`      | Maßnahme löschen (kaskadiert Kommentare)  |
| GET     | `/api/export/clipboard`      | Assistenten-Text (Systemprompt + Logs + offene Probleme) |
| GET     | `/api/export/logs`           | Log-Export als Textdatei                  |
| GET     | `/api/export/full`           | Vollexport (Logs + Probleme + Maßnahmen)  |
| POST    | `/api/admin/config`          | Konfiguration speichern                   |
