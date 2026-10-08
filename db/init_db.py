"""
Initialisiert die SQLite-Datenbank für den AI Athletik- & Ernährungs-Coach.

Erstellt folgende Tabellen:
  - nutrition_log:         Einzelne Mahlzeit-Einträge (manuell erfasst)
  - daily_health_metrics:  Garmin-/Manuelle Gesundheitsdaten pro Tag
  - workouts:              Einzelne Trainingseinheiten
  - favorites:             Häufig gegessene Lebensmittel (Schnelleintrag)
  - profile:               Körperdaten, Ziele und Einstellungen (eine Zeile, JSON)
  - claude_usage:          Token-Verbrauch der Claude-Anfragen
  - daily_summary (VIEW):  Aggregierte Tagesübersicht über alle Tabellen

Idempotent: Kann beliebig oft ausgeführt werden (CREATE IF NOT EXISTS).
"""

import sqlite3
import os
import sys

try:
    from db.paths import DB_PATH
except ImportError:  # Direkt als Skript gestartet: python db/init_db.py
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from db.paths import DB_PATH


def _add_columns(cursor, table: str, columns: dict) -> None:
    """Fuegt fehlende Spalten hinzu (Migration fuer bestehende Datenbanken)."""
    existing = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}
    for name, col_type in columns.items():
        if name not in existing:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {name} {col_type}")


def init_database(db_path: str = DB_PATH, verbose: bool = True) -> None:
    """Erstellt alle Tabellen und Views in der SQLite-Datenbank."""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ──────────────────────────────────────────────
    # Tabelle: nutrition_log
    # Speichert einzelne Lebensmittel-Einträge (manuell vom User erfasst)
    # ──────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS nutrition_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            date          TEXT    NOT NULL,                        -- ISO-Datum YYYY-MM-DD
            meal_label    TEXT    CHECK(meal_label IN (
                              'breakfast', 'lunch', 'dinner', 'snack'
                          )),
            food_name     TEXT    NOT NULL,
            amount_g      REAL,                                   -- Menge in Gramm
            calories      REAL    DEFAULT 0,                      -- kcal
            protein_g     REAL    DEFAULT 0,
            carbs_g       REAL    DEFAULT 0,
            fat_g         REAL    DEFAULT 0,
            fiber_g       REAL    DEFAULT 0,
            created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Index für schnelle Tagesabfragen
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_nutrition_date
        ON nutrition_log(date)
    """)

    # Erweiterte Nährwerte, Preis und Herkunft (Claude-Suche / Mensa-Speiseplan)
    _add_columns(cursor, "nutrition_log", {
        "amount_text": "TEXT",   # z.B. "1 Pizza", "0,5 L"
        "sugar_g":     "REAL",
        "satfat_g":    "REAL",
        "salt_g":      "REAL",
        "price_eur":   "REAL",   # bezahlter Preis
        "source":      "TEXT",   # URL oder 'Schätzung'
        "notes":       "TEXT",
    })

    # ──────────────────────────────────────────────
    # Tabelle: favorites
    # Häufig gegessene Lebensmittel für den Schnelleintrag
    # ──────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            food_name     TEXT    NOT NULL,
            amount_text   TEXT,
            calories      REAL,
            protein_g     REAL,
            carbs_g       REAL,
            sugar_g       REAL,
            fat_g         REAL,
            satfat_g      REAL,
            fiber_g       REAL,
            salt_g        REAL,
            price_eur     REAL,
            source        TEXT,
            notes         TEXT,
            created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ──────────────────────────────────────────────
    # Tabelle: profile
    # Genau eine Zeile mit Körperdaten, Zielen und Einstellungen als JSON
    # ──────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profile (
            id          INTEGER PRIMARY KEY CHECK(id = 1),
            data        TEXT    NOT NULL,
            updated_at  TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ──────────────────────────────────────────────
    # Tabelle: claude_usage
    # Verbrauch jeder Claude-Anfrage + gemeldeter Limit-Stand
    # ──────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS claude_usage (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            at            TEXT    NOT NULL,
            kind          TEXT,                                   -- lookup, advice, report, limit-check
            model         TEXT,
            input_tokens  INTEGER DEFAULT 0,
            cache_write   INTEGER DEFAULT 0,
            cache_read    INTEGER DEFAULT 0,
            output_tokens INTEGER DEFAULT 0,
            web_searches  INTEGER DEFAULT 0,
            cost_usd      REAL    DEFAULT 0,                      -- API-Gegenwert, nicht bezahlt
            duration_ms   INTEGER DEFAULT 0,
            rate_limit    TEXT                                    -- JSON aus rate_limit_event
        )
    """)

    # ──────────────────────────────────────────────
    # Tabelle: daily_health_metrics
    # Ein Eintrag pro Tag – Garmin-Daten oder manuelle Eingabe
    # ──────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS daily_health_metrics (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            date               TEXT    NOT NULL UNIQUE,           -- ISO-Datum, ein Eintrag pro Tag
            hrv_avg            REAL,                              -- Durchschnittliche HRV (ms)
            hrv_status         TEXT,                              -- z.B. 'balanced', 'low', 'high'
            sleep_score        INTEGER,                           -- 0–100
            sleep_hours        REAL,                              -- Schlafdauer in Stunden
            resting_hr         INTEGER,                           -- Ruhepuls (bpm)
            body_battery_high  INTEGER,                           -- Body Battery Max
            body_battery_low   INTEGER,                           -- Body Battery Min
            stress_avg         INTEGER,                           -- Durchschn. Stress (0–100)
            steps              INTEGER,
            active_calories    INTEGER,
            source             TEXT    DEFAULT 'garmin'            -- 'garmin' oder 'manual'
                               CHECK(source IN ('garmin', 'manual')),
            updated_at         TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ──────────────────────────────────────────────
    # Tabelle: workouts
    # Einzelne Trainingseinheiten pro Tag (mehrere pro Tag möglich)
    # ──────────────────────────────────────────────
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workouts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            date             TEXT    NOT NULL,                    -- ISO-Datum
            activity_type    TEXT,                                -- Running, Cycling, Strength…
            duration_min     REAL,                                -- Dauer in Minuten
            distance_km      REAL,                                -- Distanz (falls zutreffend)
            avg_hr           INTEGER,                             -- Durchschn. Herzfrequenz
            max_hr           INTEGER,                             -- Max. Herzfrequenz
            calories_burned  INTEGER,
            training_load    REAL,                                -- EPOC / Trainingsbelastung
            notes            TEXT,
            created_at       TEXT    DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_workouts_date
        ON workouts(date)
    """)

    # ──────────────────────────────────────────────
    # View: daily_summary
    # Aggregiert Ernährung, Health-Metriken und Workouts pro Tag
    # ──────────────────────────────────────────────
    cursor.execute("DROP VIEW IF EXISTS daily_summary")
    cursor.execute("""
        CREATE VIEW daily_summary AS
        SELECT
            -- Datum aus allen Quellen vereinen
            d.date,

            -- Ernährungs-Aggregate
            COALESCE(n.total_calories, 0)       AS total_calories,
            COALESCE(n.total_protein_g, 0)      AS total_protein_g,
            COALESCE(n.total_carbs_g, 0)        AS total_carbs_g,
            COALESCE(n.total_fat_g, 0)          AS total_fat_g,
            COALESCE(n.total_fiber_g, 0)        AS total_fiber_g,
            COALESCE(n.meal_count, 0)           AS meal_count,
            COALESCE(n.total_price_eur, 0)      AS total_price_eur,

            -- Health-Metriken
            h.hrv_avg,
            h.hrv_status,
            h.sleep_score,
            h.sleep_hours,
            h.resting_hr,
            h.body_battery_high,
            h.body_battery_low,
            h.stress_avg,
            h.steps,
            h.active_calories,
            h.source                            AS health_source,

            -- Workout-Aggregate
            COALESCE(w.workout_count, 0)        AS workout_count,
            COALESCE(w.total_workout_min, 0)    AS total_workout_min,
            COALESCE(w.total_calories_burned, 0) AS total_calories_burned

        FROM (
            -- Alle einzigartigen Daten aus allen Tabellen
            SELECT date FROM nutrition_log
            UNION
            SELECT date FROM daily_health_metrics
            UNION
            SELECT date FROM workouts
        ) d

        LEFT JOIN (
            SELECT
                date,
                SUM(calories)   AS total_calories,
                SUM(protein_g)  AS total_protein_g,
                SUM(carbs_g)    AS total_carbs_g,
                SUM(fat_g)      AS total_fat_g,
                SUM(fiber_g)    AS total_fiber_g,
                COUNT(*)        AS meal_count,
                SUM(price_eur)  AS total_price_eur
            FROM nutrition_log
            GROUP BY date
        ) n ON d.date = n.date

        LEFT JOIN daily_health_metrics h ON d.date = h.date

        LEFT JOIN (
            SELECT
                date,
                COUNT(*)          AS workout_count,
                SUM(duration_min) AS total_workout_min,
                SUM(calories_burned) AS total_calories_burned
            FROM workouts
            GROUP BY date
        ) w ON d.date = w.date

        ORDER BY d.date DESC
    """)

    conn.commit()
    conn.close()
    if verbose:
        print(f"[OK] Datenbank initialisiert: {db_path}")
        print("     Tabellen: nutrition_log, daily_health_metrics, workouts, favorites, profile, claude_usage")
        print("     Views:    daily_summary")


if __name__ == "__main__":
    init_database()
