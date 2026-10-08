"""
Pure DB-Funktionen – importierbar, kein subprocess, kein stdout.

Alle Funktionen geben dicts zurueck.
Fehler werden als Python-Exceptions geworfen.
"""

import json
import sqlite3
import os
from datetime import datetime, timedelta

from db.paths import DB_PATH

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
    amount_text: str | None = None,
    sugar_g: float | None = None,
    satfat_g: float | None = None,
    salt_g: float | None = None,
    price_eur: float | None = None,
    source: str | None = None,
    notes: str | None = None,
) -> dict:
    """Fuegt einen Lebensmittel-Eintrag hinzu."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO nutrition_log
           (date, meal_label, food_name, amount_g, calories, protein_g, carbs_g, fat_g, fiber_g,
            amount_text, sugar_g, satfat_g, salt_g, price_eur, source, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (date or _today_iso(), meal_label, food_name, amount_g, calories,
         protein_g, carbs_g, fat_g, fiber_g,
         amount_text, sugar_g, satfat_g, salt_g, price_eur, source, notes),
    )
    conn.commit()
    return {"id": cursor.lastrowid, "message": "Eintrag hinzugefuegt"}


FOOD_FIELDS = (
    "date", "meal_label", "food_name", "amount_g", "amount_text", "calories", "protein_g",
    "carbs_g", "sugar_g", "fat_g", "satfat_g", "fiber_g", "salt_g", "price_eur", "source", "notes",
)


def update_food(entry_id: int, **fields) -> dict:
    """Aktualisiert einen Eintrag (nur uebergebene Felder)."""
    updates = {k: v for k, v in fields.items() if k in FOOD_FIELDS}
    if updates:
        conn = get_connection()
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE nutrition_log SET {assignments} WHERE id = ?", (*updates.values(), entry_id))
        conn.commit()
    return get_food(entry_id)


def get_food(entry_id: int) -> dict | None:
    conn = get_connection()
    return _row_to_dict(conn.execute("SELECT * FROM nutrition_log WHERE id = ?", (entry_id,)).fetchone())


def get_food_range(start_date: str, end_date: str) -> list[dict]:
    """Alle Eintraege in einem Datumsbereich (fuer Verlauf und Kosten)."""
    conn = get_connection()
    return _rows_to_list(conn.execute(
        "SELECT * FROM nutrition_log WHERE date BETWEEN ? AND ? ORDER BY date, created_at",
        (start_date, end_date),
    ).fetchall())


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
                   COALESCE(SUM(sugar_g), 0)    AS total_sugar_g,
                   COALESCE(SUM(satfat_g), 0)   AS total_satfat_g,
                   COALESCE(SUM(salt_g), 0)     AS total_salt_g,
                   COALESCE(SUM(price_eur), 0)  AS total_price_eur,
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


def replace_workouts(date: str, workouts: list[dict]) -> int:
    """Ersetzt die Workouts eines Tages (Garmin-Sync darf mehrfach laufen, ohne zu duplizieren)."""
    conn = get_connection()
    conn.execute("DELETE FROM workouts WHERE date = ?", (date,))
    for w in workouts:
        conn.execute(
            """INSERT INTO workouts
                   (date, activity_type, duration_min, distance_km,
                    avg_hr, max_hr, calories_burned, training_load, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (date, w.get("activity_type"), w.get("duration_min"), w.get("distance_km"),
             w.get("avg_hr"), w.get("max_hr"), w.get("calories_burned"), w.get("training_load"),
             w.get("notes")),
        )
    conn.commit()
    return len(workouts)


def synced_dates(start_date: str, end_date: str) -> set[str]:
    """Tage, fuer die schon Garmin-Daten vorliegen."""
    conn = get_connection()
    return {r["date"] for r in conn.execute(
        "SELECT date FROM daily_health_metrics WHERE source = 'garmin' AND date BETWEEN ? AND ?",
        (start_date, end_date),
    ).fetchall()}


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


# ── Favoriten ────────────────────────────────────────────────────

FAVORITE_FIELDS = (
    "food_name", "amount_text", "calories", "protein_g", "carbs_g", "sugar_g", "fat_g",
    "satfat_g", "fiber_g", "salt_g", "price_eur", "source", "notes",
)


def list_favorites() -> list[dict]:
    conn = get_connection()
    return _rows_to_list(conn.execute("SELECT * FROM favorites ORDER BY food_name COLLATE NOCASE").fetchall())


def add_favorite(**fields) -> dict:
    data = {k: fields.get(k) for k in FAVORITE_FIELDS}
    conn = get_connection()
    cursor = conn.execute(
        f"INSERT INTO favorites ({', '.join(data)}) VALUES ({', '.join('?' for _ in data)})",
        tuple(data.values()),
    )
    conn.commit()
    return _row_to_dict(conn.execute("SELECT * FROM favorites WHERE id = ?", (cursor.lastrowid,)).fetchone())


def update_favorite(fav_id: int, **fields) -> dict | None:
    updates = {k: v for k, v in fields.items() if k in FAVORITE_FIELDS}
    conn = get_connection()
    if updates:
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE favorites SET {assignments} WHERE id = ?", (*updates.values(), fav_id))
        conn.commit()
    return _row_to_dict(conn.execute("SELECT * FROM favorites WHERE id = ?", (fav_id,)).fetchone())


def delete_favorite(fav_id: int) -> dict:
    conn = get_connection()
    conn.execute("DELETE FROM favorites WHERE id = ?", (fav_id,))
    conn.commit()
    return {"deleted_id": fav_id}


# ── Profil (Koerperdaten, Ziele, Einstellungen) ──────────────────

DEFAULT_PROFILE = {
    "name": "",
    "sex": "m",
    "age": 22,
    "heightCm": 180,
    "weightKg": 75,
    "bodyFat": "",
    "activity": 1.2,          # Alltag ohne Sport
    "strengthDays": 0,
    "cardioDays": 0,
    "goal": "maintain",       # lose | recomp | maintain | muscle | gain
    "proteinPerKg": "",       # leer = automatisch je nach Ziel
    "targetWeightKg": "",
    "useGarmin": True,        # Kalorienziel an Garmin-Aktivitaet anpassen
    "priceGroup": "Studierende",
    "dailyBudget": 12,
    "diet": "",
    "questionLevel": "normal",
    "claudeModel": "sonnet",
    "claudePath": "",
    "garminWeightSync": True,  # Gewicht/Koerperfett bei jedem Sync aus Garmin uebernehmen
    "onboarded": False,
}


def get_profile() -> dict:
    conn = get_connection()
    row = conn.execute("SELECT data FROM profile WHERE id = 1").fetchone()
    stored = json.loads(row["data"]) if row else {}
    return {**DEFAULT_PROFILE, **stored}


def save_profile(data: dict) -> dict:
    profile = {**get_profile(), **{k: v for k, v in data.items() if k in DEFAULT_PROFILE}}
    conn = get_connection()
    conn.execute(
        """INSERT INTO profile (id, data) VALUES (1, ?)
           ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = CURRENT_TIMESTAMP""",
        (json.dumps(profile, ensure_ascii=False),),
    )
    conn.commit()
    return profile


# ── Claude-Verbrauch ─────────────────────────────────────────────

def log_claude_usage(entry: dict) -> dict:
    conn = get_connection()
    conn.execute(
        """INSERT INTO claude_usage
               (at, kind, model, input_tokens, cache_write, cache_read, output_tokens,
                web_searches, cost_usd, duration_ms, rate_limit)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (entry["at"], entry["kind"], entry["model"], entry["input"], entry["cacheWrite"],
         entry["cacheRead"], entry["output"], entry["webSearches"], entry["costUsd"],
         entry["durationMs"], json.dumps(entry["rateLimit"]) if entry.get("rateLimit") else None),
    )
    conn.commit()
    return entry


def _usage_row(row: dict) -> dict:
    total = row["input_tokens"] + row["cache_write"] + row["cache_read"] + row["output_tokens"]
    return {
        "at": row["at"], "kind": row["kind"], "model": row["model"],
        "input": row["input_tokens"], "cacheWrite": row["cache_write"], "cacheRead": row["cache_read"],
        "output": row["output_tokens"], "webSearches": row["web_searches"], "costUsd": row["cost_usd"],
        "durationMs": row["duration_ms"], "total": total,
    }


def get_claude_usage(limit: int = 200) -> dict:
    """Letzte Anfragen + juengster bekannter Limit-Stand."""
    conn = get_connection()
    rows = _rows_to_list(conn.execute(
        "SELECT * FROM claude_usage ORDER BY id DESC LIMIT ?", (limit,)
    ).fetchall())
    latest = conn.execute(
        "SELECT at, rate_limit FROM claude_usage WHERE rate_limit IS NOT NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return {
        "rateLimit": json.loads(latest["rate_limit"]) if latest else None,
        "updatedAt": latest["at"] if latest else None,
        "log": [_usage_row(r) for r in rows],
    }
