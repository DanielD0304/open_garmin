"""
Garmin Connect Daten-Fetcher mit Session-Caching.

Holt HRV, Sleep, Heart Rate, Body Battery, Stress, Steps und Workouts
von Garmin Connect und gibt sie als JSON auf stdout aus.

Session-Token wird in .garmin_session/ gecacht, um Rate-Limiting
und staendige 2FA-Prompts zu vermeiden.

Verwendung:
  python garmin/fetch_garmin.py --date 2024-01-15
  python garmin/fetch_garmin.py                     # heute

Fehler-Handling:
  Bei Login-Fehler (Captcha/2FA) wird KEIN Crash ausgeloest, sondern:
  {"status": "error", "message": "2FA required"} ausgegeben.

Umgebungsvariablen (oder .env-Datei im Projektroot):
  GARMIN_EMAIL    – Garmin Connect E-Mail
  GARMIN_PASSWORD – Garmin Connect Passwort
"""

import json
import os
import sys
import argparse
from datetime import datetime, date

# Pfade
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
SESSION_DIR = os.path.join(SCRIPT_DIR, ".garmin_session")
ENV_FILE = os.path.join(PROJECT_DIR, ".env")


# ── Helpers ──────────────────────────────────────────────────────

def output_success(data):
    """JSON-Erfolgsausgabe auf stdout."""
    print(json.dumps({"status": "ok", "data": data}, ensure_ascii=False, default=str))
    sys.exit(0)


def output_error(message, code="error"):
    """JSON-Fehlerausgabe auf stdout – KEIN Crash."""
    print(json.dumps({"status": "error", "code": code, "message": str(message)}, ensure_ascii=False))
    sys.exit(0)  # Exit 0 damit n8n den Output parsen kann


def load_env():
    """Laedt .env-Datei falls vorhanden (einfaches key=value Format)."""
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_credentials():
    """Holt Garmin-Credentials aus Umgebungsvariablen."""
    email = os.environ.get("GARMIN_EMAIL", "").strip()
    password = os.environ.get("GARMIN_PASSWORD", "").strip()
    if not email or not password:
        output_error(
            "GARMIN_EMAIL und GARMIN_PASSWORD muessen als Umgebungsvariablen "
            "oder in der .env-Datei gesetzt sein.",
            code="missing_credentials"
        )
    return email, password


def ensure_session_dir():
    """Erstellt das Session-Verzeichnis falls noetig."""
    os.makedirs(SESSION_DIR, exist_ok=True)


# ── Garmin Login mit Session-Cache ───────────────────────────────

def get_garmin_client(max_retries: int = 2):
    """
    Erstellt einen authentifizierten Garmin-Client.

    1. Versucht zuerst, ein gecachtes Session-Token zu laden.
    2. Falls abgelaufen: automatischer Re-Login mit Email/Passwort.
    3. Speichert das neue Token fuer zukuenftige Aufrufe.
    4. Bei Rate-Limiting: exponentielles Backoff (max 2 Retries).

    Bei 2FA/Captcha-Fehlern wird ein strukturierter JSON-Fehler ausgegeben
    mit `requires_action: "2fa"` fuer Frontend-Erkennung.
    """
    import time

    try:
        from garminconnect import Garmin
    except ImportError:
        output_error(
            "garminconnect nicht installiert. "
            "Bitte ausfuehren: pip install garminconnect",
            code="missing_dependency"
        )

    ensure_session_dir()
    email, password = get_credentials()

    garmin = Garmin(email, password)

    # 1. Versuch: Session-Token laden
    try:
        garmin.login(SESSION_DIR)
        # Validierung: teste ob das Token noch gueltig ist
        try:
            garmin.get_full_name()
            return garmin
        except Exception:
            print("[Garmin] Gecachtes Token abgelaufen, versuche Re-Login...", file=sys.stderr)
    except Exception:
        pass  # Token nicht vorhanden oder beschaedigt

    # 2. Versuch: Frischer Login (mit Retry bei Rate-Limiting)
    for attempt in range(max_retries + 1):
        try:
            garmin.login()
            # Session-Token fuer naechstes Mal speichern
            garmin.garth.dump(SESSION_DIR)
            print("[Garmin] Neues Session-Token gespeichert.", file=sys.stderr)
            return garmin
        except Exception as e:
            error_msg = str(e).lower()

            # 2FA/Captcha – kein Retry moeglich
            if any(kw in error_msg for kw in ["captcha", "2fa", "mfa", "verification"]):
                output_error(
                    "2FA/Captcha erforderlich. Bitte manuell bei Garmin Connect "
                    "einloggen oder die Daten manuell im Dashboard eingeben.",
                    code="2fa_required"
                )

            # Rate-Limiting – Backoff und Retry
            if "rate" in error_msg or "limit" in error_msg or "429" in error_msg:
                if attempt < max_retries:
                    wait = 2 ** (attempt + 1)  # 2s, 4s
                    print(f"[Garmin] Rate-Limited. Warte {wait}s... (Versuch {attempt + 1}/{max_retries})", file=sys.stderr)
                    time.sleep(wait)
                    continue
                output_error(
                    "Rate-Limit erreicht nach mehreren Versuchen. Bitte spaeter erneut versuchen.",
                    code="rate_limited"
                )

            # Anderer Fehler – kein Retry
            output_error(
                f"Garmin Login fehlgeschlagen: {e}",
                code="login_failed"
            )


def check_session_status():
    """Prueft den Status der Garmin-Session ohne Login-Versuch."""
    session_files = []
    if os.path.exists(SESSION_DIR):
        session_files = os.listdir(SESSION_DIR)

    return {
        "session_exists": len(session_files) > 0,
        "session_dir": SESSION_DIR,
        "session_files": len(session_files),
    }


# ── Daten abrufen ────────────────────────────────────────────────

def fetch_health_data(garmin, target_date, raw_out: dict | None = None):
    """
    Holt alle relevanten Gesundheitsdaten fuer ein Datum.

    raw_out (optional) wird mit den unveraenderten API-Antworten befuellt.
    Garmin ist eine inoffizielle API - wenn dort ein Feld umbenannt wird,
    faellt das Mapping unten still auf None zurueck. Mit den Rohdaten laesst
    sich die Historie spaeter neu parsen statt verloren zu sein.
    """
    date_str = target_date.isoformat()
    health = {}

    def keep(kind, payload):
        if raw_out is not None and payload is not None:
            raw_out[kind] = payload

    # HRV
    try:
        hrv_data = garmin.get_hrv_data(date_str)
        keep("hrv", hrv_data)
        if hrv_data:
            summary = hrv_data.get("hrvSummary", {}) or {}
            health["hrv_avg"] = summary.get("weeklyAvg") or summary.get("lastNightAvg")
            health["hrv_status"] = summary.get("status", "").lower() if summary.get("status") else None
    except Exception:
        health["hrv_avg"] = None
        health["hrv_status"] = None

    # Sleep
    try:
        sleep_data = garmin.get_sleep_data(date_str)
        keep("sleep", sleep_data)
        if sleep_data:
            daily_sleep = sleep_data.get("dailySleepDTO", {}) or {}
            health["sleep_score"] = daily_sleep.get("sleepScores", {}).get("overall", {}).get("value")
            sleep_secs = daily_sleep.get("sleepTimeSeconds")
            health["sleep_hours"] = round(sleep_secs / 3600, 1) if sleep_secs else None
    except Exception:
        health["sleep_score"] = None
        health["sleep_hours"] = None

    # Resting Heart Rate
    try:
        hr_data = garmin.get_rhr_day(date_str)
        keep("rhr", hr_data)
        if hr_data:
            for entry in hr_data.get("allMetrics", {}).get("metricsMap", {}).get("WELLNESS_RESTING_HEART_RATE", []):
                if entry.get("calendarDate") == date_str:
                    health["resting_hr"] = entry.get("value")
                    break
            else:
                health["resting_hr"] = None
        else:
            health["resting_hr"] = None
    except Exception:
        health["resting_hr"] = None

    # Body Battery
    try:
        bb_data = garmin.get_body_battery(date_str)
        keep("body_battery", bb_data)
        if bb_data and isinstance(bb_data, list) and len(bb_data) > 0:
            charged_values = [e.get("charged", 0) for e in bb_data if e.get("charged") is not None]
            drained_values = [e.get("drained", 0) for e in bb_data if e.get("drained") is not None]
            if charged_values:
                health["body_battery_high"] = max(charged_values)
                health["body_battery_low"] = min(drained_values) if drained_values else 0
            else:
                health["body_battery_high"] = None
                health["body_battery_low"] = None
        else:
            health["body_battery_high"] = None
            health["body_battery_low"] = None
    except Exception:
        health["body_battery_high"] = None
        health["body_battery_low"] = None

    # Stress
    try:
        stress_data = garmin.get_stress_data(date_str)
        keep("stress", stress_data)
        if stress_data:
            health["stress_avg"] = stress_data.get("overallStressLevel")
        else:
            health["stress_avg"] = None
    except Exception:
        health["stress_avg"] = None

    # Steps + Active Calories (aus daily stats)
    try:
        stats = garmin.get_stats(date_str)
        keep("stats", stats)
        if stats:
            health["steps"] = stats.get("totalSteps")
            health["active_calories"] = stats.get("activeKilocalories")
        else:
            health["steps"] = None
            health["active_calories"] = None
    except Exception:
        health["steps"] = None
        health["active_calories"] = None

    return health


def fetch_workouts(garmin, target_date, raw_out: dict | None = None):
    """Holt alle Workouts/Aktivitaeten fuer ein Datum."""
    date_str = target_date.isoformat()
    workouts = []

    try:
        activities = garmin.get_activities_by_date(date_str, date_str, "")
        if raw_out is not None and activities:
            raw_out["activities"] = activities
        if not activities:
            return workouts

        for act in activities:
            workout = {
                "activity_type": act.get("activityType", {}).get("typeKey", "unknown"),
                "duration_min": round(act.get("duration", 0) / 60, 1) if act.get("duration") else None,
                "distance_km": round(act.get("distance", 0) / 1000, 2) if act.get("distance") else None,
                "avg_hr": act.get("averageHR"),
                "max_hr": act.get("maxHR"),
                "calories_burned": act.get("calories"),
                "training_load": act.get("activityTrainingLoad"),
            }
            workouts.append(workout)
    except Exception as e:
        print(f"[Garmin Fetch Error] Workouts konnten nicht geladen werden: {e}", file=sys.stderr)

    return workouts


# ── Main ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Garmin Connect Daten-Fetcher mit Session-Caching"
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Datum im Format YYYY-MM-DD (Standard: heute)",
    )
    args = parser.parse_args()

    # .env laden
    load_env()

    # Ziel-Datum bestimmen
    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            output_error(f"Ungueltiges Datumsformat: {args.date}. Erwartet: YYYY-MM-DD")
    else:
        target_date = date.today()

    # Garmin-Client authentifizieren
    garmin = get_garmin_client()

    # Daten abrufen
    health = fetch_health_data(garmin, target_date)
    workouts = fetch_workouts(garmin, target_date)

    output_success({
        "date": target_date.isoformat(),
        "health": health,
        "workouts": workouts,
        "source": "garmin",
    })


if __name__ == "__main__":
    main()
