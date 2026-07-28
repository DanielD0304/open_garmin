"""
Schema-Migrationen fuer coach.db.

Bisher bestand das Schema nur aus CREATE TABLE IF NOT EXISTS. Neue Spalten
wurden auf bestehenden Datenbanken damit still ignoriert. Stattdessen jetzt
eine versionierte Migrationsliste ueber PRAGMA user_version.

Neue Aenderung? Neuen Eintrag ans Ende von MIGRATIONS haengen, nie einen
bestehenden Eintrag editieren - bestehende DBs haben ihn schon angewendet.
"""

from __future__ import annotations

import sqlite3

# (version, description, sql)
MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "Basis-Schema: nutrition_log, daily_health_metrics, workouts",
        """
        CREATE TABLE IF NOT EXISTS nutrition_log (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            date          TEXT    NOT NULL,
            meal_label    TEXT    CHECK(meal_label IN (
                              'breakfast', 'lunch', 'dinner', 'snack'
                          )),
            food_name     TEXT    NOT NULL,
            amount_g      REAL,
            calories      REAL    DEFAULT 0,
            protein_g     REAL    DEFAULT 0,
            carbs_g       REAL    DEFAULT 0,
            fat_g         REAL    DEFAULT 0,
            fiber_g       REAL    DEFAULT 0,
            created_at    TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_nutrition_date ON nutrition_log(date);

        CREATE TABLE IF NOT EXISTS daily_health_metrics (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            date               TEXT    NOT NULL UNIQUE,
            hrv_avg            REAL,
            hrv_status         TEXT,
            sleep_score        INTEGER,
            sleep_hours        REAL,
            resting_hr         INTEGER,
            body_battery_high  INTEGER,
            body_battery_low   INTEGER,
            stress_avg         INTEGER,
            steps              INTEGER,
            active_calories    INTEGER,
            source             TEXT    DEFAULT 'garmin'
                               CHECK(source IN ('garmin', 'manual')),
            updated_at         TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS workouts (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            date             TEXT    NOT NULL,
            activity_type    TEXT,
            duration_min     REAL,
            distance_km      REAL,
            avg_hr           INTEGER,
            max_hr           INTEGER,
            calories_burned  INTEGER,
            training_load    REAL,
            notes            TEXT,
            created_at       TEXT    DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_workouts_date ON workouts(date);
        """,
    ),
    (
        2,
        "Rohdaten von Garmin aufbewahren (Schutz vor stillem Feldverlust)",
        """
        CREATE TABLE IF NOT EXISTS raw_garmin_payloads (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT NOT NULL,
            kind        TEXT NOT NULL,          -- hrv, sleep, rhr, body_battery, stress, stats, activities
            payload     TEXT NOT NULL,          -- unveraenderte API-Antwort als JSON
            fetched_at  TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_raw_payload_date ON raw_garmin_payloads(date, kind);
        """,
    ),
]

LATEST_VERSION = MIGRATIONS[-1][0]


def get_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def run_migrations(conn: sqlite3.Connection, verbose: bool = False) -> int:
    """Wendet alle ausstehenden Migrationen an. Gibt die neue Version zurueck."""
    current = get_version(conn)

    for version, description, sql in MIGRATIONS:
        if version <= current:
            continue
        if verbose:
            print(f"[Migration {version}] {description}")
        conn.executescript(sql)
        # PRAGMA erlaubt keine Platzhalter; version stammt aus der Konstante oben.
        conn.execute(f"PRAGMA user_version = {int(version)}")
        conn.commit()
        current = version

    return current


def ensure_views(conn: sqlite3.Connection) -> None:
    """Views bei jedem Start neu bauen - sie folgen dem Tabellen-Schema."""
    conn.execute("DROP VIEW IF EXISTS daily_summary")
    conn.execute("""
        CREATE VIEW daily_summary AS
        SELECT
            d.date,
            COALESCE(n.total_calories, 0)       AS total_calories,
            COALESCE(n.total_protein_g, 0)      AS total_protein_g,
            COALESCE(n.total_carbs_g, 0)        AS total_carbs_g,
            COALESCE(n.total_fat_g, 0)          AS total_fat_g,
            COALESCE(n.total_fiber_g, 0)        AS total_fiber_g,
            COALESCE(n.meal_count, 0)           AS meal_count,
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
            COALESCE(w.workout_count, 0)        AS workout_count,
            COALESCE(w.total_workout_min, 0)    AS total_workout_min,
            COALESCE(w.total_calories_burned, 0) AS total_calories_burned
        FROM (
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
                COUNT(*)        AS meal_count
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
