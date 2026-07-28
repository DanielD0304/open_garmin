"""Gemeinsame Test-Fixtures. Jeder Test bekommt eine frische SQLite-Datei."""

import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from db import models  # noqa: E402
from db.init_db import init_database  # noqa: E402


@pytest.fixture
def temp_db(tmp_path):
    """Frische, migrierte Datenbank; models zeigt fuer die Testdauer darauf."""
    original = models.DB_PATH
    db_file = tmp_path / "test_coach.db"

    init_database(str(db_file), verbose=False)
    models.set_db_path(str(db_file))

    yield db_file

    models.close_all_connections()
    models.set_db_path(original)


@pytest.fixture
def no_ai_key(monkeypatch):
    """Stellt sicher, dass kein echter API-Key aus der .env in Tests wirkt."""
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.setenv("AI_API_KEY", "")
