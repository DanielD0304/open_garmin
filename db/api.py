"""
DB CLI-API – Duenner Wrapper um models.py fuer Shell-Nutzung.

Alle Kernlogik lebt in models.py. Diese Datei bietet nur das
argparse-Interface und JSON-Output auf stdout.

Verwendung:
  python db/api.py add_food --date 2024-01-15 --food-name "Skyr" --calories 85
  python db/api.py get_food_log --date 2024-01-15
  python db/api.py delete_food --id 3
  python db/api.py add_health --date 2024-01-15 --hrv-avg 48 --sleep-score 82
  python db/api.py get_health --date 2024-01-15
  python db/api.py add_workout --date 2024-01-15 --activity-type Running --duration-min 45
  python db/api.py get_summary --days 7
"""

import argparse
import json
import sys
import os

# models.py liegt im selben Verzeichnis
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db import models  # noqa: E402


def output_success(data):
    print(json.dumps({"status": "ok", "data": data}, ensure_ascii=False))
    sys.exit(0)


def output_error(message):
    print(json.dumps({"status": "error", "message": str(message)}, ensure_ascii=False))
    sys.exit(1)


# ── Kommando-Handler (delegieren an models.py) ───────────────────

def cmd_add_food(args):
    result = models.add_food(
        food_name=args.food_name,
        date=args.date,
        meal_label=args.meal_label,
        amount_g=args.amount_g,
        calories=args.calories,
        protein_g=args.protein_g,
        carbs_g=args.carbs_g,
        fat_g=args.fat_g,
        fiber_g=args.fiber_g,
    )
    output_success(result)


def cmd_delete_food(args):
    result = models.delete_food(args.id)
    output_success(result)


def cmd_get_food_log(args):
    result = models.get_food_log(args.date)
    output_success(result)


def cmd_add_health(args):
    result = models.add_health(
        date=args.date,
        hrv_avg=args.hrv_avg,
        hrv_status=args.hrv_status,
        sleep_score=args.sleep_score,
        sleep_hours=args.sleep_hours,
        resting_hr=args.resting_hr,
        body_battery_high=args.body_battery_high,
        body_battery_low=args.body_battery_low,
        stress_avg=args.stress_avg,
        steps=args.steps,
        active_calories=args.active_calories,
        source=args.source or "manual",
    )
    output_success(result)


def cmd_get_health(args):
    result = models.get_health(args.date)
    output_success(result)


def cmd_add_workout(args):
    result = models.add_workout(
        date=args.date,
        activity_type=args.activity_type,
        duration_min=args.duration_min,
        distance_km=args.distance_km,
        avg_hr=args.avg_hr,
        max_hr=args.max_hr,
        calories_burned=args.calories_burned,
        training_load=args.training_load,
        notes=args.notes,
    )
    output_success(result)


def cmd_get_summary(args):
    result = models.get_summary(args.days or 7)
    output_success(result)


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
