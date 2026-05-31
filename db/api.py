"""
DB CLI-API fuer n8n Execute Command Nodes.

Jede Aktion ist ein argparse-Subcommand. Output ist immer JSON auf stdout.
Fehler werden als {"status":"error","message":"..."} ausgegeben.

Verwendung (n8n Execute Command):
  python db/api.py add_food --date 2024-01-15 --food-name "Skyr" --calories 85 --protein-g 15
  python db/api.py get_food_log --date 2024-01-15
  python db/api.py delete_food --id 3
  python db/api.py add_health --date 2024-01-15 --hrv-avg 48 --sleep-score 82
  python db/api.py get_health --date 2024-01-15
  python db/api.py add_workout --date 2024-01-15 --activity-type Running --duration-min 45
  python db/api.py get_summary --days 7
"""

import argparse
import sqlite3
import json
import sys
import os
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coach.db")


# ── Helpers ──────────────────────────────────────────────────────

def get_connection():
    """Oeffnet eine SQLite-Verbindung mit Row-Factory."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def output_success(data):
    """Gibt ein Erfolgs-JSON auf stdout aus."""
    print(json.dumps({"status": "ok", "data": data}, ensure_ascii=False))
    sys.exit(0)


def output_error(message):
    """Gibt ein Fehler-JSON auf stdout aus und beendet mit Exit-Code 1."""
    print(json.dumps({"status": "error", "message": str(message)}, ensure_ascii=False))
    sys.exit(1)


def row_to_dict(row):
    """Konvertiert eine sqlite3.Row zu einem dict."""
    return dict(row) if row else None


def rows_to_list(rows):
    """Konvertiert eine Liste von sqlite3.Row zu einer Liste von dicts."""
    return [dict(r) for r in rows]


def today_iso():
    """Gibt das heutige Datum als ISO-String zurueck."""
    return datetime.now().strftime("%Y-%m-%d")


# ── Aktion: add_food ────────────────────────────────────────────

def cmd_add_food(args):
    """Fuegt einen Lebensmittel-Eintrag zur nutrition_log-Tabelle hinzu."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO nutrition_log
               (date, meal_label, food_name, amount_g, calories, protein_g, carbs_g, fat_g, fiber_g)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                args.date or today_iso(),
                args.meal_label,
                args.food_name,
                args.amount_g,
                args.calories,
                args.protein_g,
                args.carbs_g,
                args.fat_g,
                args.fiber_g,
            ),
        )
        conn.commit()
        output_success({"id": cursor.lastrowid, "message": "Eintrag hinzugefuegt"})
    except Exception as e:
        output_error(f"add_food fehlgeschlagen: {e}")
    finally:
        conn.close()


# ── Aktion: delete_food ─────────────────────────────────────────

def cmd_delete_food(args):
    """Loescht einen Eintrag aus nutrition_log anhand der ID."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM nutrition_log WHERE id = ?", (args.id,))
        conn.commit()
        output_success({"deleted_id": args.id})
    except Exception as e:
        output_error(f"delete_food fehlgeschlagen: {e}")
    finally:
        conn.close()


# ── Aktion: get_food_log ────────────────────────────────────────

def cmd_get_food_log(args):
    """Gibt alle Eintraege fuer ein Datum zurueck + Makro-Summen."""
    date = args.date or today_iso()
    conn = get_connection()
    try:
        entries = rows_to_list(
            conn.execute(
                "SELECT * FROM nutrition_log WHERE date = ? ORDER BY created_at",
                (date,),
            ).fetchall()
        )
        # Makro-Summen
        totals = row_to_dict(
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
        output_success({"date": date, "entries": entries, "totals": totals})
    except Exception as e:
        output_error(f"get_food_log fehlgeschlagen: {e}")
    finally:
        conn.close()


# ── Aktion: add_health ──────────────────────────────────────────

def cmd_add_health(args):
    """Speichert oder aktualisiert die Gesundheitsmetriken fuer einen Tag (UPSERT)."""
    date = args.date or today_iso()
    conn = get_connection()
    try:
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
            (
                date,
                args.hrv_avg,
                args.hrv_status,
                args.sleep_score,
                args.sleep_hours,
                args.resting_hr,
                args.body_battery_high,
                args.body_battery_low,
                args.stress_avg,
                args.steps,
                args.active_calories,
                args.source or "manual",
            ),
        )
        conn.commit()
        output_success({"date": date, "message": "Gesundheitsdaten gespeichert"})
    except Exception as e:
        output_error(f"add_health fehlgeschlagen: {e}")
    finally:
        conn.close()


# ── Aktion: get_health ──────────────────────────────────────────

def cmd_get_health(args):
    """Gibt Gesundheitsmetriken und Workouts fuer ein Datum zurueck."""
    date = args.date or today_iso()
    conn = get_connection()
    try:
        health = row_to_dict(
            conn.execute(
                "SELECT * FROM daily_health_metrics WHERE date = ?", (date,)
            ).fetchone()
        )
        workouts = rows_to_list(
            conn.execute(
                "SELECT * FROM workouts WHERE date = ? ORDER BY created_at", (date,)
            ).fetchall()
        )
        output_success({"date": date, "health": health, "workouts": workouts})
    except Exception as e:
        output_error(f"get_health fehlgeschlagen: {e}")
    finally:
        conn.close()


# ── Aktion: add_workout ─────────────────────────────────────────

def cmd_add_workout(args):
    """Fuegt ein einzelnes Workout hinzu."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO workouts
                   (date, activity_type, duration_min, distance_km,
                    avg_hr, max_hr, calories_burned, training_load, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                args.date or today_iso(),
                args.activity_type,
                args.duration_min,
                args.distance_km,
                args.avg_hr,
                args.max_hr,
                args.calories_burned,
                args.training_load,
                args.notes,
            ),
        )
        conn.commit()
        output_success({"id": cursor.lastrowid, "message": "Workout hinzugefuegt"})
    except Exception as e:
        output_error(f"add_workout fehlgeschlagen: {e}")
    finally:
        conn.close()


# ── Aktion: get_summary ─────────────────────────────────────────

def cmd_get_summary(args):
    """
    Gibt die aggregierte Zusammenfassung der letzten N Tage zurueck.
    WICHTIG: Fuer den AI-Report werden NUR Health- und Workout-Daten verwendet.
    Ernaehrungsdaten werden hier bewusst ausgeschlossen.
    """
    days = args.days or 7
    end_date = today_iso()
    start_date = (datetime.now() - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    conn = get_connection()

    try:
        # Health-Metriken der letzten N Tage
        health_rows = rows_to_list(
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

        # Workouts der letzten N Tage
        workout_rows = rows_to_list(
            conn.execute(
                """SELECT date, activity_type, duration_min, distance_km,
                          avg_hr, max_hr, calories_burned, training_load, notes
                   FROM workouts
                   WHERE date BETWEEN ? AND ?
                   ORDER BY date DESC""",
                (start_date, end_date),
            ).fetchall()
        )

        # Workout-Aggregate
        workout_summary = row_to_dict(
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

        # Health-Durchschnitte
        health_averages = row_to_dict(
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

        output_success({
            "period": {"start": start_date, "end": end_date, "days": days},
            "health_daily": health_rows,
            "health_averages": health_averages,
            "workouts": workout_rows,
            "workout_summary": workout_summary,
        })
    except Exception as e:
        output_error(f"get_summary fehlgeschlagen: {e}")
    finally:
        conn.close()


# ── Main: Argparse Setup ────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="DB CLI-API fuer den AI Athletik-Coach"
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    # ── add_food ──
    p = subparsers.add_parser("add_food", help="Lebensmittel hinzufuegen")
    p.add_argument("--date", default=None)
    p.add_argument("--meal-label", default="snack",
                   choices=["breakfast", "lunch", "dinner", "snack"])
    p.add_argument("--food-name", required=True)
    p.add_argument("--amount-g", type=float, default=None)
    p.add_argument("--calories", type=float, default=0)
    p.add_argument("--protein-g", type=float, default=0)
    p.add_argument("--carbs-g", type=float, default=0)
    p.add_argument("--fat-g", type=float, default=0)
    p.add_argument("--fiber-g", type=float, default=0)
    p.set_defaults(func=cmd_add_food)

    # ── delete_food ──
    p = subparsers.add_parser("delete_food", help="Lebensmittel loeschen")
    p.add_argument("--id", type=int, required=True)
    p.set_defaults(func=cmd_delete_food)

    # ── get_food_log ──
    p = subparsers.add_parser("get_food_log", help="Tages-Ernaehrungslog abrufen")
    p.add_argument("--date", default=None)
    p.set_defaults(func=cmd_get_food_log)

    # ── add_health ──
    p = subparsers.add_parser("add_health", help="Gesundheitsdaten speichern (UPSERT)")
    p.add_argument("--date", default=None)
    p.add_argument("--hrv-avg", type=float, default=None)
    p.add_argument("--hrv-status", default=None)
    p.add_argument("--sleep-score", type=int, default=None)
    p.add_argument("--sleep-hours", type=float, default=None)
    p.add_argument("--resting-hr", type=int, default=None)
    p.add_argument("--body-battery-high", type=int, default=None)
    p.add_argument("--body-battery-low", type=int, default=None)
    p.add_argument("--stress-avg", type=int, default=None)
    p.add_argument("--steps", type=int, default=None)
    p.add_argument("--active-calories", type=int, default=None)
    p.add_argument("--source", default="manual", choices=["garmin", "manual"])
    p.set_defaults(func=cmd_add_health)

    # ── get_health ──
    p = subparsers.add_parser("get_health", help="Tages-Health + Workouts abrufen")
    p.add_argument("--date", default=None)
    p.set_defaults(func=cmd_get_health)

    # ── add_workout ──
    p = subparsers.add_parser("add_workout", help="Workout hinzufuegen")
    p.add_argument("--date", default=None)
    p.add_argument("--activity-type", default=None)
    p.add_argument("--duration-min", type=float, default=None)
    p.add_argument("--distance-km", type=float, default=None)
    p.add_argument("--avg-hr", type=int, default=None)
    p.add_argument("--max-hr", type=int, default=None)
    p.add_argument("--calories-burned", type=int, default=None)
    p.add_argument("--training-load", type=float, default=None)
    p.add_argument("--notes", default=None)
    p.set_defaults(func=cmd_add_workout)

    # ── get_summary ──
    p = subparsers.add_parser("get_summary", help="N-Tage-Zusammenfassung (Health+Workouts)")
    p.add_argument("--days", type=int, default=7)
    p.set_defaults(func=cmd_get_summary)

    args = parser.parse_args()

    try:
        args.func(args)
    except Exception as e:
        output_error(str(e))


if __name__ == "__main__":
    main()
