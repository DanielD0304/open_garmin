"""Migrationen: Versionierung, Idempotenz, Upgrade einer Alt-DB."""

import sqlite3

from db.init_db import init_database
from db.migrations import LATEST_VERSION, get_version, run_migrations


def table_names(db_file) -> set[str]:
    conn = sqlite3.connect(str(db_file))
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows}


def test_fresh_db_is_at_latest_version(tmp_path):
    db_file = tmp_path / "fresh.db"
    version = init_database(str(db_file), verbose=False)

    assert version == LATEST_VERSION
    assert {"nutrition_log", "daily_health_metrics", "workouts", "raw_garmin_payloads"} <= table_names(db_file)


def test_running_twice_changes_nothing(tmp_path):
    db_file = tmp_path / "twice.db"
    first = init_database(str(db_file), verbose=False)
    second = init_database(str(db_file), verbose=False)

    assert first == second == LATEST_VERSION


def test_legacy_db_without_version_gets_upgraded(tmp_path):
    """Alt-DBs haben user_version=0, aber die Basistabellen schon."""
    db_file = tmp_path / "legacy.db"
    conn = sqlite3.connect(str(db_file))
    conn.executescript("""
        CREATE TABLE nutrition_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, meal_label TEXT, food_name TEXT NOT NULL,
            amount_g REAL, calories REAL DEFAULT 0, protein_g REAL DEFAULT 0,
            carbs_g REAL DEFAULT 0, fat_g REAL DEFAULT 0, fiber_g REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE daily_health_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL UNIQUE,
            hrv_avg REAL, hrv_status TEXT, sleep_score INTEGER, sleep_hours REAL,
            resting_hr INTEGER, body_battery_high INTEGER, body_battery_low INTEGER,
            stress_avg INTEGER, steps INTEGER, active_calories INTEGER,
            source TEXT DEFAULT 'garmin', updated_at TEXT
        );
        CREATE TABLE workouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL,
            activity_type TEXT, duration_min REAL, distance_km REAL, avg_hr INTEGER,
            max_hr INTEGER, calories_burned INTEGER, training_load REAL, notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.execute(
        "INSERT INTO daily_health_metrics (date, hrv_avg) VALUES ('2026-01-01', 55)"
    )
    conn.commit()
    assert get_version(conn) == 0
    conn.close()

    version = init_database(str(db_file), verbose=False)

    assert version == LATEST_VERSION
    assert "raw_garmin_payloads" in table_names(db_file)

    # Bestehende Daten ueberleben die Migration
    conn = sqlite3.connect(str(db_file))
    try:
        row = conn.execute(
            "SELECT hrv_avg FROM daily_health_metrics WHERE date = '2026-01-01'"
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == 55


def test_pending_migration_is_applied_only_once(tmp_path):
    db_file = tmp_path / "pending.db"
    conn = sqlite3.connect(str(db_file))
    try:
        run_migrations(conn)
        assert get_version(conn) == LATEST_VERSION
        # Zweiter Lauf darf nicht an bestehenden Objekten scheitern
        run_migrations(conn)
        assert get_version(conn) == LATEST_VERSION
    finally:
        conn.close()
