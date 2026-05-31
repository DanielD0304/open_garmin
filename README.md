# AI Athletik- & Ernährungs-Coach

Lokales Dashboard für Trainings-/Erholungsdaten (Garmin) und Ernährung mit KI-Coaching-Report.

## Projektstruktur

```
open_garmin/
├── db/
│   ├── init_db.py          # SQLite-Schema (idempotent)
│   ├── api.py              # CLI-API für n8n (argparse → JSON)
│   ├── http_server.py      # Lokaler HTTP-Wrapper für n8n
│   └── coach.db            # SQLite-Datenbank
├── frontend/
│   ├── index.html          # Dashboard
│   ├── index.css           # Design-System
│   └── app.js              # Async Fetch-Logik
├── garmin/
│   ├── fetch_garmin.py     # Garmin Connect Fetcher
│   └── .garmin_session/    # Gecachtes Session-Token
├── n8n/
│   └── workflows_all.json  # Alle 7 Workflows zum Import
├── .env.example            # Vorlage für Garmin-Credentials
├── .gitignore
└── venv/                   # Python 3.12 (garminconnect)
```

## Setup

### 1. Python venv (bereits erstellt)
```bash
python -m venv venv
venv\Scripts\pip install garminconnect
```

### 2. Datenbank initialisieren
```bash
venv\Scripts\python db\init_db.py
```

### 3. Garmin Credentials
```bash
copy .env
```

### 4. Lokalen API-Wrapper starten
In einem zweiten Terminal:
```bash
venv\Scripts\python db\http_server.py
```
Der Wrapper lauscht auf `http://localhost:8765/run` und wird von den n8n-Workflows verwendet.

### 5. n8n starten und Workflows importieren
```bash
./scripts/import_n8n_workflows.ps1
```
Das Skript startet n8n per Docker Compose, importiert die 7 Workflows, veröffentlicht sie und startet n8n danach einmal neu.

### 6. Ollama (für AI-Report)
```bash
ollama pull gemma2
ollama serve
```

### 7. Frontend öffnen
`frontend/index.html` im Browser öffnen.

Die n8n-Workflows sprechen den lokalen Wrapper über `host.docker.internal:8765` an. Auf Docker Desktop unter Windows ist diese Adresse aus dem Container erreichbar.

## DB CLI-API Referenz

```bash
# Ernährung
python db/api.py add_food --date 2024-01-15 --food-name "Skyr" --calories 85 --protein-g 15
python db/api.py get_food_log --date 2024-01-15
python db/api.py delete_food --id 3

# Gesundheit
python db/api.py add_health --date 2024-01-15 --hrv-avg 48 --sleep-score 82 --source manual
python db/api.py get_health --date 2024-01-15

# Workouts
python db/api.py add_workout --date 2024-01-15 --activity-type Running --duration-min 45

# Report (nur Health + Workouts, keine Ernährung)
python db/api.py get_summary --days 7
```
