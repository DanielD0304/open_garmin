"""
Zentrale Datenpfade der Desktop-App.

Alle veraenderlichen Daten liegen im Benutzerordner (beschreibbar, auch wenn die
App als .exe unter "Programme" liegt):  %LOCALAPPDATA%\\AI Coach\\
Ueberschreibbar per Umgebungsvariable AI_COACH_DATA (z.B. fuer Tests).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "AI Coach"


def _default_data_dir() -> Path:
    if os.environ.get("AI_COACH_DATA"):
        return Path(os.environ["AI_COACH_DATA"])
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def resource_dir() -> Path:
    """Ordner mit mitgelieferten Dateien (frontend/). In der .exe: PyInstaller-Bundle."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


DATA_DIR = _default_data_dir()
DB_PATH = DATA_DIR / "coach.db"
GARMIN_SESSION_DIR = DATA_DIR / "garmin_session"
CLAUDE_WORKDIR = DATA_DIR / "claude-workdir"
LOG_DIR = DATA_DIR / "logs"
FRONTEND_DIR = resource_dir() / "frontend"

for _d in (DATA_DIR, GARMIN_SESSION_DIR, CLAUDE_WORKDIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Einmalige Uebernahme einer bestehenden Repo-Datenbank (vor der Desktop-App: db/coach.db)
_legacy_db = Path(__file__).resolve().parent / "coach.db"
if not DB_PATH.exists() and _legacy_db.exists() and not getattr(sys, "frozen", False):
    shutil.copy2(_legacy_db, DB_PATH)
