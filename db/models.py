"""
Pure DB-Funktionen – importierbar, kein subprocess, kein stdout.

Alle Funktionen geben dicts zurueck.
Fehler werden als Python-Exceptions geworfen.
"""

import sqlite3
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coach.db")

_connection: sqlite3.Connection | None = None


# ── Connection Management ────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """Gibt eine geteilte SQLite-Verbindung zurueck (Singleton pro Prozess)."""
    global _connection
    if _connection is None:
        _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
        _connection.row_factory = sqlite3.Row
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA foreign_keys=ON")
    return _connection


def close_connection():
    """Schliesst die geteilte Verbindung."""
    global _connection
    if _connection is not None:
        _connection.close()
        _connection = None


def _row_to_dict(row) -> dict | None:
    return dict(row) if row else None


def _rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


def _today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ── Nutrition ────────────────────────────────────────────────────

def add_food(
    food_name: str,
    date: str | None = None,
    meal_label: str = "snack",
    amount_g: float | None = None,
    calories: float = 0,
    protein_g: float = 0,
    carbs_g: float = 0,
    fat_g: float = 0,
    fiber_g: float = 0,
) -> dict:
    """Fuegt einen Lebensmittel-Eintrag hinzu."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO nutrition_log
           (date, meal_label, food_name, amount_g, calories, protein_g, carbs_g, fat_g, fiber_g)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (date or _today_iso(), meal_label, food_name, amount_g, calories,
         protein_g, carbs_g, fat_g, fiber_g),
    )
    conn.commit()
    return {"id": cursor.lastrowid, "message": "Eintrag hinzugefuegt"}


def delete_food(entry_id: int) -> dict:
    """Loescht einen Eintrag aus nutrition_log."""
    conn = get_connection()
    conn.execute("DELETE FROM nutrition_log WHERE id = ?", (entry_id,))
    conn.commit()
    return {"deleted_id": entry_id}


def get_food_log(date: str | None = None) -> dict:
    """Gibt alle Eintraege fuer ein Datum + Makro-Summen zurueck."""
    date = date or _today_iso()
    conn = get_connection()

    entries = _rows_to_list(
        conn.execute(
            "SELECT * FROM nutrition_log WHERE date = ? ORDER BY created_at",
            (date,),
        ).fetchall()
    )

    totals = _row_to_dict(
        conn.execute(
            """SELECT
                   COALESCE(SUM(calories), 0)   AS total_calories,
                   COALESCE(SUM(protein_g), 0)  AS total_protein_g,
                   COALESCE(SUM(carbs_g), 0)    AS total_carbs_g,
                   COALESCE(SUM(fat_g), 0)      AS total_fat_g,
                   COALESCE(SUM(fiber_g), 0)    AS total_fiber_g,
                   COUNT(*)                     AS meal_count
               FROM nutrition_log WHERE date = ?""",
            (date,),
        ).fetchone()
    )

    return {"date": date, "entries": entries, "totals": totals}


# ── Health ───────────────────────────────────────────────────────

def add_health(
    date: str | None = None,
    hrv_avg: float | None = None,
    hrv_status: str | None = None,
    sleep_score: int | None = None,
    sleep_hours: float | None = None,
    resting_hr: int | None = None,
    body_battery_high: int | None = None,
    body_battery_low: int | None = None,
    stress_avg: int | None = None,
    steps: int | None = None,
    active_calories: int | None = None,
    source: str = "manual",
) -> dict:
    """Speichert/aktualisiert Gesundheitsmetriken (UPSERT)."""
    date = date or _today_iso()
    conn = get_connection()
    conn.execute(
        """INSERT INTO daily_health_metrics
               (date, hrv_avg, hrv_status, sleep_score, sleep_hours,
                resting_hr, body_battery_high, body_battery_low,
                stress_avg, steps, active_calories, source)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(date) DO UPDATE SET
               hrv_avg          = COALESCE(excluded.hrv_avg, hrv_avg),
               hrv_status       = COALESCE(excluded.hrv_status, hrv_status),
               sleep_score      = COALESCE(excluded.sleep_score, sleep_score),
               sleep_hours      = COALESCE(excluded.sleep_hours, sleep_hours),
               resting_hr       = COALESCE(excluded.resting_hr, resting_hr),
               body_battery_high = COALESCE(excluded.body_battery_high, body_battery_high),
               body_battery_low  = COALESCE(excluded.body_battery_low, body_battery_low),
               stress_avg       = COALESCE(excluded.stress_avg, stress_avg),
               steps            = COALESCE(excluded.steps, steps),
               active_calories  = COALESCE(excluded.active_calories, active_calories),
               source           = excluded.source,
               updated_at       = CURRENT_TIMESTAMP""",
        (date, hrv_avg, hrv_status, sleep_score, sleep_hours,
         resting_hr, body_battery_high, body_battery_low,
         stress_avg, steps, active_calories, source),
    )
    conn.commit()
    return {"date": date, "message": "Gesundheitsdaten gespeichert"}


def get_health(date: str | None = None) -> dict:
    """Gibt Gesundheitsmetriken und Workouts fuer ein Datum zurueck."""
    date = date or _today_iso()
    conn = get_connection()

    health = _row_to_dict(
        conn.execute(
            "SELECT * FROM daily_health_metrics WHERE date = ?", (date,)
        ).fetchone()
    )

    workouts = _rows_to_list(
        conn.execute(
            "SELECT * FROM workouts WHERE date = ? ORDER BY created_at", (date,)
        ).fetchall()
    )

    return {"date": date, "health": health, "workouts": workouts}


# ── Workouts ─────────────────────────────────────────────────────

def add_workout(
    date: str | None = None,
    activity_type: str | None = None,
    duration_min: float | None = None,
    distance_km: float | None = None,
    avg_hr: int | None = None,
    max_hr: int | None = None,
    calories_burned: int | None = None,
    training_load: float | None = None,
    notes: str | None = None,
) -> dict:
    """Fuegt ein Workout hinzu."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO workouts
               (date, activity_type, duration_min, distance_km,
                avg_hr, max_hr, calories_burned, training_load, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (date or _today_iso(), activity_type, duration_min, distance_km,
         avg_hr, max_hr, calories_burned, training_load, notes),
    )
    conn.commit()
    return {"id": cursor.lastrowid, "message": "Workout hinzugefuegt"}


# ── Summary (nur Health + Workouts, KEINE Ernaehrung) ────────────

def get_summary(days: int = 7) -> dict:
    """Aggregierte Zusammenfassung der letzten N Tage."""
    end_date = _today_iso()
    start_date = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    conn = get_connection()

    health_rows = _rows_to_list(
        conn.execute(
            """SELECT date, hrv_avg, hrv_status, sleep_score, sleep_hours,
                      resting_hr, body_battery_high, body_battery_low,
                      stress_avg, steps, active_calories, source
               FROM daily_health_metrics
               WHERE date BETWEEN ? AND ?
               ORDER BY date DESC""",
            (start_date, end_date),
        ).fetchall()
    )

    workout_rows = _rows_to_list(
        conn.execute(
            """SELECT date, activity_type, duration_min, distance_km,
                      avg_hr, max_hr, calories_burned, training_load, notes
               FROM workouts
               WHERE date BETWEEN ? AND ?
               ORDER BY date DESC""",
            (start_date, end_date),
        ).fetchall()
    )

    workout_summary = _row_to_dict(
        conn.execute(
            """SELECT
                   COUNT(*)              AS total_workouts,
                   COALESCE(SUM(duration_min), 0) AS total_duration_min,
                   COALESCE(SUM(calories_burned), 0) AS total_calories_burned,
                   COALESCE(AVG(avg_hr), 0) AS avg_heart_rate
               FROM workouts
               WHERE date BETWEEN ? AND ?""",
            (start_date, end_date),
        ).fetchone()
    )

    health_averages = _row_to_dict(
        conn.execute(
            """SELECT
                   ROUND(AVG(hrv_avg), 1)          AS avg_hrv,
                   ROUND(AVG(sleep_score), 0)      AS avg_sleep_score,
                   ROUND(AVG(sleep_hours), 1)      AS avg_sleep_hours,
                   ROUND(AVG(resting_hr), 0)       AS avg_resting_hr,
                   ROUND(AVG(stress_avg), 0)       AS avg_stress,
                   ROUND(AVG(steps), 0)            AS avg_steps
               FROM daily_health_metrics
               WHERE date BETWEEN ? AND ?""",
            (start_date, end_date),
        ).fetchone()
    )

    return {
        "period": {"start": start_date, "end": end_date, "days": days},
        "health_daily": health_rows,
        "health_averages": health_averages,
        "workouts": workout_rows,
        "workout_summary": workout_summary,
    }
