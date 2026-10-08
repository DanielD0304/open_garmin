# AI Coach – Training, Erholung & Ernährung

Desktop-App für Windows: Garmin-Daten (HRV, Schlaf, Stress, Schritte, Workouts) und Ernährung in einem Programm.
Die KI-Funktionen laufen über dein **Claude-Abo** (Claude Code CLI). Du brauchst keinen API-Key und kein lokales Modell.

## Funktionen

- **Ernährung mit Claude**: Freitext wie „Pizza Margherita im Pizzawerk“ oder „1 L Cola von Lidl“. Claude sucht Nährwerte
  und Preis heraus und **fragt nach**, wenn etwas unklar ist, z.B. Marke, Variante oder Gebinde. Für die Mensen des
  Studierendenwerks Karlsruhe liest die App den Speiseplan selbst und gibt Claude die exakten Werte und Preise mit.
- **Tagesziel aus Körperprofil + Garmin**: Grundumsatz aus deinen Körperdaten plus die aktiven kcal, die deine Uhr gemessen hat,
  plus Zu- oder Abschlag für dein Ziel (Fett verlieren, Recomp, halten, Muskelaufbau, zunehmen).
  Ohne Garmin-Daten wird der Bedarf aus Alltag und Training geschätzt.
- **Favoriten** als Schnellknöpfe, **Kosten** pro Tag, Woche und Monat gegen dein Tagesbudget.
- **Garmin**: Login mit 2FA direkt in der App, automatischer Sync beim Start, Körperdaten (Gewicht, Körperfett) aus Garmin.
- **Coach-Report** und **„Was fehlt mir heute noch?“**: Claude wertet Training, Erholung und Ernährung zusammen aus.
- **Claude-Limit** immer sichtbar: Wie viel Prozent deines 5-Stunden- und Wochenlimits verbraucht sind, plus Tokens pro Anfrage.

## Installation

### 1. Claude Code CLI (einmalig)

```powershell
irm https://claude.ai/install.ps1 | iex
claude          # im Terminal starten, dann /login → "Claude account with subscription"
```

Die App findet die CLI automatisch (`~\.local\bin`, PATH oder die Version der Claude-Desktop-App).
Claude läuft im schlanken Modus, ohne Plugins, Skills und MCP. Es darf nur im Web suchen und Seiten lesen und braucht
pro Suche etwa 4–12k Tokens.

### 2. App bauen

```powershell
.\scripts\build_exe.ps1          # erstellt dist\AI Coach\AI Coach.exe
.\scripts\install_shortcuts.ps1  # Startmenü + Desktop
```

### 3. Erster Start

Die App öffnet „Profil & Ziele“. Dort verbindest du Garmin (E-Mail, Passwort, ggf. 2FA-Code) und übernimmst die Körperdaten
mit „Daten aus Garmin übernehmen“. Das Passwort wird nicht gespeichert, nur das Sitzungs-Token von Garmin.

## Daten

Alles liegt lokal in `%LOCALAPPDATA%\AI Coach\`:

| Pfad | Inhalt |
|------|--------|
| `coach.db` | SQLite: Ernährung, Favoriten, Profil, Garmin-Daten, Claude-Verbrauch |
| `garmin_session\` | Garmin-Sitzungs-Token |
| `logs\app.log` | Protokoll der App |

Daten aus dem früheren Node-Ernährungstracker übernehmen:

```powershell
.\venv\Scripts\python scripts\import_ernaehrungstracker.py
```

## Entwicklung

```powershell
python -m venv venv
.\venv\Scripts\pip install -r requirements.txt
.\venv\Scripts\python app.py               # Desktop-Fenster
.\venv\Scripts\python -m db.server         # nur Server, im Browser: http://127.0.0.1:8765/
.\venv\Scripts\python -m pytest tests      # Tests
```

### Projektstruktur

```
app.py                  Desktop-Start: Server im Hintergrund + Programmfenster (pywebview)
db/
  server.py             FastAPI: Ernährung, Favoriten, Profil, Ziele, Garmin, Claude, Report
  models.py             SQLite-Zugriff
  init_db.py            Schema + idempotente Migration
  targets.py            Tagesziel aus Körperprofil + Garmin-Aktivität
  claude_client.py      Claude Code CLI (Abo), Prompts, Verbrauchsprotokoll
  mensa.py              Speiseplan-Parser sw-ka.de
  paths.py              Datenordner der App
garmin/fetch_garmin.py  Garmin-Login (2FA), Health, Workouts, Körperprofil
frontend/               Oberfläche (HTML/CSS/JS)
packaging/              PyInstaller-Spec + Icon
scripts/                Build, Verknüpfungen, Datenimport
tests/                  pytest
```
