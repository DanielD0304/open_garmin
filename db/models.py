"""
Pure DB-Funktionen – importierbar, kein subprocess, kein stdout.

Alle Funktionen geben dicts zurueck.
Fehler werden als Python-Exceptions geworfen.
"""

import json
import sqlite3
import os
import threading
from datetime import datetime, timedelta

DB_PATH = os.environ.get("COACH_DB_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "coach.db"
)

# Eine Verbindung pro Thread. FastAPI fuehrt sync-Handler im Threadpool aus,
# und eine sqlite3-Verbindung darf nicht ungeschuetzt zwischen Threads wandern.
_local = threading.local()
_all_connections: set[sqlite3.Connection] = set()
_registry_lock = threading.Lock()


# ── Connection Management ────────────────────────────────────────

def get_connection() -> sqlite3.Connection:
    """Gibt die SQLite-Verbindung des aktuellen Threads zurueck."""
    conn = getattr(_local, "connection", None)
    if conn is None:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        # Warten statt sofort "database is locked" werfen, wenn ein anderer
        # Thread gerade schreibt.
        conn.execute("PRAGMA busy_timeout=5000")
        _local.connection = conn
        with _registry_lock:
            _all_connections.add(conn)
    return conn


def close_connection():
    """Schliesst die Verbindung des aktuellen Threads."""
    conn = getattr(_local, "connection", None)
    if conn is not None:
        conn.close()
        _local.connection = None
        with _registry_lock:
            _all_connections.discard(conn)


def close_all_connections():
    """Schliesst alle Thread-Verbindungen (Shutdown)."""
    close_connection()
    with _registry_lock:
        connections = list(_all_connections)
        _all_connections.clear()
    for conn in connections:
        try:
            conn.close()
        except sqlite3.Error:
            pass


def set_db_path(path: str) -> None:
    """Wechselt die Datenbankdatei (fuer Tests). Schliesst alle Verbindungen."""
    global DB_PATH
    close_all_connections()
    DB_PATH = path


def _row_to_dict(row) -> dict | None:
    return dict(row) if row else None


def _rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


def _today_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _window(days: int) -> tuple[str, str]:
    """
    Gibt (start_date, end_date) fuer die letzten N Tage zurueck.

    Beide Grenzen stammen aus derselben Uhrzeit-Abfrage - vorher las jede
    Funktion die Uhr zweimal, was ueber Mitternacht ein inkonsistentes
    Fenster ergeben konnte.
    """
    end_date = _today_iso()
    start_date = (
        datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=days - 1)
    ).strftime("%Y-%m-%d")
    return start_date, end_date


# ── Garmin Rohdaten ──────────────────────────────────────────────

def save_raw_payload(date: str, kind: str, payload) -> dict:
    """
    Legt die unveraenderte Garmin-Antwort ab.

    Garmin ist eine inoffizielle API: Wenn dort ein Feld umbenannt wird,
    liefert das Mapping in fetch_garmin.py stillschweigend None. Mit dem
    Rohpayload laesst sich die Historie spaeter neu parsen statt neu holen
    (Garmin gibt alte Tage nicht unbegrenzt heraus).
    """
    conn = get_connection()
    cursor = conn.execute(
        "INSERT INTO raw_garmin_payloads (date, kind, payload) VALUES (?, ?, ?)",
        (date, kind, json.dumps(payload, ensure_ascii=False, default=str)),
    )
    conn.commit()
    return {"id": cursor.lastrowid, "date": date, "kind": kind}


def get_raw_payloads(date: str, kind: str | None = None) -> list[dict]:
    """Liest die Rohpayloads eines Tages (optional nach Typ gefiltert)."""
    conn = get_connection()
    if kind:
        rows = conn.execute(
            "SELECT * FROM raw_garmin_payloads WHERE date = ? AND kind = ? ORDER BY fetched_at DESC",
            (date, kind),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM raw_garmin_payloads WHERE date = ? ORDER BY fetched_at DESC",
            (date,),
        ).fetchall()

    result = []
    for row in _rows_to_list(rows):
        try:
            row["payload"] = json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError):
            pass
        result.append(row)
    return result


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
    start_date, end_date = _window(days)
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


# ── Daily Overview (Charts) ─────────────────────────────────────

def get_daily_overview(days: int = 14) -> list[dict]:
    """Aggregated per-day data for charts: health + nutrition + workouts."""
    start_date, end_date = _window(days)
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            h.date,
            h.hrv_avg,
            h.sleep_score,
            h.sleep_hours,
            h.resting_hr,
            h.stress_avg,
            h.steps,
            h.active_calories,
            COALESCE(n.total_calories_in, 0)  AS total_calories_in,
            COALESCE(n.total_protein_g, 0)    AS total_protein_g,
            COALESCE(n.total_carbs_g, 0)      AS total_carbs_g,
            COALESCE(n.total_fat_g, 0)        AS total_fat_g,
            COALESCE(w.workout_count, 0)      AS workout_count,
            COALESCE(w.total_workout_min, 0)  AS total_workout_min
        FROM daily_health_metrics h
        LEFT JOIN (
            SELECT date,
                   SUM(calories)  AS total_calories_in,
                   SUM(protein_g) AS total_protein_g,
                   SUM(carbs_g)   AS total_carbs_g,
                   SUM(fat_g)     AS total_fat_g
            FROM nutrition_log
            GROUP BY date
        ) n ON n.date = h.date
        LEFT JOIN (
            SELECT date,
                   COUNT(*)           AS workout_count,
                   SUM(duration_min)  AS total_workout_min
            FROM workouts
            GROUP BY date
        ) w ON w.date = h.date
        WHERE h.date BETWEEN ? AND ?
        ORDER BY h.date ASC
        """,
        (start_date, end_date),
    ).fetchall()

    return _rows_to_list(rows)


# ── Nutrition Summary ────────────────────────────────────────────

def get_nutrition_summary(days: int = 7) -> list[dict]:
    """Per-day nutrition aggregates for the last N days."""
    start_date, end_date = _window(days)
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            date,
            COALESCE(SUM(calories), 0)   AS total_calories,
            COALESCE(SUM(protein_g), 0)  AS total_protein_g,
            COALESCE(SUM(carbs_g), 0)    AS total_carbs_g,
            COALESCE(SUM(fat_g), 0)      AS total_fat_g,
            COALESCE(SUM(fiber_g), 0)    AS total_fiber_g,
            COUNT(*)                     AS meal_count
        FROM nutrition_log
        WHERE date BETWEEN ? AND ?
        GROUP BY date
        ORDER BY date ASC
        """,
        (start_date, end_date),
    ).fetchall()

    return _rows_to_list(rows)


# ── Coaching Context (AI Reports) ────────────────────────────────

def _linear_trend(values: list[float | None]) -> str:
    """Simple linear regression slope -> 'rising', 'falling', or 'stable'."""
    clean = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(clean) < 2:
        return "stable"
    n = len(clean)
    sum_x = sum(x for x, _ in clean)
    sum_y = sum(y for _, y in clean)
    sum_xy = sum(x * y for x, y in clean)
    sum_x2 = sum(x * x for x, _ in clean)
    denom = n * sum_x2 - sum_x * sum_x
    if denom == 0:
        return "stable"
    slope = (n * sum_xy - sum_x * sum_y) / denom
    # Normalise slope relative to mean to decide threshold
    mean_y = sum_y / n
    if mean_y == 0:
        return "stable"
    relative = slope / abs(mean_y)
    if relative > 0.02:
        return "rising"
    if relative < -0.02:
        return "falling"
    return "stable"


def get_coaching_context(days: int = 7) -> dict:
    """Enriched data for AI coaching: summary + nutrition + trends + correlations."""
    summary = get_summary(days)
    nutrition_daily = get_nutrition_summary(days)

    # ── Trend calculation ────────────────────────────────────────
    health_rows = summary.get("health_daily") or []
    # Rows are ordered DESC from get_summary, reverse for chronological
    health_chrono = list(reversed(health_rows))

    hrv_vals = [d.get("hrv_avg") for d in health_chrono]
    sleep_vals = [d.get("sleep_score") for d in health_chrono]
    stress_vals = [d.get("stress_avg") for d in health_chrono]

    trends = {
        "hrv_trend": _linear_trend(hrv_vals),
        "sleep_trend": _linear_trend(sleep_vals),
        "stress_trend": _linear_trend(stress_vals),
    }

    # ── Correlation detection ────────────────────────────────────
    correlations: list[str] = []

    # 1) High stress vs low sleep
    paired_stress_sleep = [
        (d.get("stress_avg"), d.get("sleep_score"))
        for d in health_chrono
        if d.get("stress_avg") is not None and d.get("sleep_score") is not None
    ]
    if len(paired_stress_sleep) >= 3:
        high_stress_days = [s for st, s in paired_stress_sleep if st >= 50]
        low_stress_days = [s for st, s in paired_stress_sleep if st < 50]
        if high_stress_days and low_stress_days:
            avg_sleep_high_stress = sum(high_stress_days) / len(high_stress_days)
            avg_sleep_low_stress = sum(low_stress_days) / len(low_stress_days)
            if avg_sleep_high_stress < avg_sleep_low_stress - 5:
                correlations.append(
                    "High-stress days correlate with lower sleep scores "
                    f"(avg {avg_sleep_high_stress:.0f} vs {avg_sleep_low_stress:.0f})."
                )

    # 2) Workout days vs sleep quality
    workout_dates = {w.get("date") for w in (summary.get("workouts") or [])}
    workout_sleep = []
    rest_sleep = []
    for d in health_chrono:
        ss = d.get("sleep_score")
        if ss is None:
            continue
        if d.get("date") in workout_dates:
            workout_sleep.append(ss)
        else:
            rest_sleep.append(ss)
    if workout_sleep and rest_sleep:
        avg_ws = sum(workout_sleep) / len(workout_sleep)
        avg_rs = sum(rest_sleep) / len(rest_sleep)
        diff = avg_ws - avg_rs
        if abs(diff) > 5:
            direction = "better" if diff > 0 else "worse"
            correlations.append(
                f"Workout days show {direction} sleep scores "
                f"(avg {avg_ws:.0f} vs {avg_rs:.0f} on rest days)."
            )

    # 3) Calorie consistency
    cal_values = [d.get("total_calories") for d in nutrition_daily if d.get("total_calories")]
    if len(cal_values) >= 3:
        mean_cal = sum(cal_values) / len(cal_values)
        if mean_cal > 0:
            variance = sum((c - mean_cal) ** 2 for c in cal_values) / len(cal_values)
            cv = (variance ** 0.5) / mean_cal  # coefficient of variation
            if cv > 0.3:
                correlations.append(
                    f"Calorie intake varies widely (CV={cv:.0%}). "
                    "More consistent daily intake may improve energy levels."
                )
            else:
                correlations.append(
                    f"Calorie intake is fairly consistent (CV={cv:.0%})."
                )

    summary["nutrition_daily"] = nutrition_daily
    summary["trends"] = trends
    summary["correlations"] = correlations
    return summary
