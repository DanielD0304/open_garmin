"""
Garmin Connect: Login (inkl. 2FA), Gesundheitsdaten, Workouts und Koerperprofil.

Gespeichert wird nur das Sitzungs-Token im Datenordner der App
(%LOCALAPPDATA%\\AI Coach\\garmin_session), nie das Passwort.

Verwendung als CLI (zum Testen):
  python garmin/fetch_garmin.py --date 2024-01-15
  python garmin/fetch_garmin.py                     # heute
Ohne gueltiges Token liest die CLI GARMIN_EMAIL / GARMIN_PASSWORD aus der Umgebung.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import date, timedelta

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from db.paths import GARMIN_SESSION_DIR  # noqa: E402

SESSION_DIR = str(GARMIN_SESSION_DIR)


# ── Fehler ───────────────────────────────────────────────────────

class GarminError(Exception):
    code = "garmin_error"


class GarminAuthRequired(GarminError):
    code = "garmin_auth_required"


class GarminMfaRequired(GarminError):
    code = "garmin_mfa_required"


class GarminRateLimited(GarminError):
    code = "rate_limited"


def _translate(e: Exception) -> GarminError:
    msg = str(e)
    low = msg.lower()
    if "429" in low or "too many" in low or "rate" in low:
        return GarminRateLimited("Garmin hat zu viele Anfragen gemeldet. Bitte später erneut versuchen.")
    if any(k in low for k in ("401", "403", "auth", "password", "credential", "token")):
        return GarminAuthRequired(f"Garmin-Anmeldung fehlgeschlagen: {msg}")
    return GarminError(f"Garmin-Fehler: {msg}")


# ── Login / Sitzung ──────────────────────────────────────────────

_pending_mfa: dict = {}  # Desktop-App mit genau einem Nutzer: offener 2FA-Vorgang


def is_connected() -> bool:
    return os.path.isdir(SESSION_DIR) and any(os.scandir(SESSION_DIR))


def get_garmin_client():
    """Client aus dem gespeicherten Token. Ohne Token → GarminAuthRequired."""
    try:
        from garminconnect import Garmin
    except ImportError as e:
        raise GarminError("garminconnect nicht installiert (pip install garminconnect)") from e
    if not is_connected():
        raise GarminAuthRequired("Nicht mit Garmin verbunden. Bitte in der App anmelden.")
    garmin = Garmin()
    try:
        garmin.login(SESSION_DIR)
    except Exception as e:
        raise _translate(e) from e
    return garmin


def login_with_credentials(email: str, password: str) -> str:
    """Meldet sich an. Rueckgabe 'ok' oder 'mfa' (dann submit_mfa aufrufen)."""
    from garminconnect import Garmin
    os.makedirs(SESSION_DIR, exist_ok=True)
    garmin = Garmin(email, password, return_on_mfa=True)
    try:
        status, state = garmin.login()
    except Exception as e:
        raise _translate(e) from e
    if status == "needs_mfa":
        _pending_mfa.clear()
        _pending_mfa.update(client=garmin, state=state)
        return "mfa"
    garmin.client.dump(SESSION_DIR)
    return "ok"


def submit_mfa(code: str) -> str:
    if not _pending_mfa:
        raise GarminAuthRequired("Kein offener 2FA-Vorgang. Bitte erneut anmelden.")
    garmin = _pending_mfa["client"]
    try:
        garmin.resume_login(_pending_mfa["state"], code.strip())
    except Exception as e:
        raise _translate(e) from e
    garmin.client.dump(SESSION_DIR)
    _pending_mfa.clear()
    return "ok"


def logout() -> None:
    shutil.rmtree(SESSION_DIR, ignore_errors=True)
    os.makedirs(SESSION_DIR, exist_ok=True)


# ── Daten abrufen ────────────────────────────────────────────────

def fetch_health_data(garmin, target_date):
    """Holt alle relevanten Gesundheitsdaten fuer ein Datum."""
    date_str = target_date.isoformat()
    health = {}

    # HRV
    try:
        hrv_data = garmin.get_hrv_data(date_str)
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
        health["resting_hr"] = None
        if hr_data:
            for entry in hr_data.get("allMetrics", {}).get("metricsMap", {}).get("WELLNESS_RESTING_HEART_RATE", []):
                if entry.get("calendarDate") == date_str:
                    health["resting_hr"] = entry.get("value")
                    break
    except Exception:
        health["resting_hr"] = None

    # Body Battery
    try:
        bb_data = garmin.get_body_battery(date_str)
        health["body_battery_high"] = None
        health["body_battery_low"] = None
        if bb_data and isinstance(bb_data, list):
            charged_values = [e.get("charged", 0) for e in bb_data if e.get("charged") is not None]
            drained_values = [e.get("drained", 0) for e in bb_data if e.get("drained") is not None]
            if charged_values:
                health["body_battery_high"] = max(charged_values)
                health["body_battery_low"] = min(drained_values) if drained_values else 0
    except Exception:
        health["body_battery_high"] = None
        health["body_battery_low"] = None

    # Stress
    try:
        stress_data = garmin.get_stress_data(date_str)
        health["stress_avg"] = stress_data.get("overallStressLevel") if stress_data else None
    except Exception:
        health["stress_avg"] = None

    # Steps + Active Calories (aus daily stats)
    try:
        stats = garmin.get_stats(date_str) or {}
        health["steps"] = stats.get("totalSteps")
        health["active_calories"] = stats.get("activeKilocalories")
    except Exception:
        health["steps"] = None
        health["active_calories"] = None

    return health


def fetch_workouts(garmin, target_date):
    """Holt alle Workouts/Aktivitaeten fuer ein Datum."""
    date_str = target_date.isoformat()
    workouts = []
    try:
        for act in garmin.get_activities_by_date(date_str, date_str, "") or []:
            workouts.append({
                "activity_type": act.get("activityType", {}).get("typeKey", "unknown"),
                "duration_min": round(act.get("duration", 0) / 60, 1) if act.get("duration") else None,
                "distance_km": round(act.get("distance", 0) / 1000, 2) if act.get("distance") else None,
                "avg_hr": act.get("averageHR"),
                "max_hr": act.get("maxHR"),
                "calories_burned": act.get("calories"),
                "training_load": act.get("activityTrainingLoad"),
            })
    except Exception as e:
        print(f"[Garmin Fetch Error] Workouts konnten nicht geladen werden: {e}", file=sys.stderr)
    return workouts


def _kg(value):
    """Garmin liefert Gewicht meist in Gramm."""
    if value in (None, ""):
        return None
    value = float(value)
    return round(value / 1000, 1) if value > 1000 else round(value, 1)


def fetch_body_profile(garmin) -> dict:
    """Geschlecht, Alter, Groesse, Gewicht und (falls vorhanden) Koerperfett aus Garmin Connect."""
    profile: dict = {}
    try:
        user = garmin.get_user_profile() or {}
        data = user.get("userData", user)
        gender = str(data.get("gender") or "").upper()
        if gender in ("MALE", "FEMALE"):
            profile["sex"] = "m" if gender == "MALE" else "f"
        if data.get("height"):
            profile["heightCm"] = round(float(data["height"]))
        if data.get("weight"):
            profile["weightKg"] = _kg(data["weight"])
        if data.get("birthDate"):
            born = date.fromisoformat(str(data["birthDate"])[:10])
            today = date.today()
            profile["age"] = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except Exception as e:
        print(f"[Garmin] Profil nicht lesbar: {e}", file=sys.stderr)

    # Neueste Waage-/Gewichtsmessung der letzten 90 Tage
    try:
        end = date.today()
        comp = garmin.get_body_composition((end - timedelta(days=90)).isoformat(), end.isoformat()) or {}
        entries = [e for e in comp.get("dateWeightList") or [] if e.get("weight")]
        if entries:
            latest = max(entries, key=lambda e: e.get("date") or e.get("calendarDate") or 0)
            profile["weightKg"] = _kg(latest["weight"])
            if latest.get("bodyFat"):
                profile["bodyFat"] = round(float(latest["bodyFat"]), 1)
            profile["weightDate"] = str(latest.get("calendarDate") or "")[:10]
    except Exception as e:
        print(f"[Garmin] Gewicht nicht lesbar: {e}", file=sys.stderr)
    return profile


# ── CLI ──────────────────────────────────────────────────────────

def _load_env():
    env_file = os.path.join(PROJECT_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main():
    parser = argparse.ArgumentParser(description="Garmin Connect Daten-Fetcher")
    parser.add_argument("--date", default=None, help="Datum YYYY-MM-DD (Standard: heute)")
    args = parser.parse_args()
    target_date = date.fromisoformat(args.date) if args.date else date.today()
    try:
        if not is_connected():
            _load_env()
            email, password = os.environ.get("GARMIN_EMAIL"), os.environ.get("GARMIN_PASSWORD")
            if not email or not password:
                raise GarminAuthRequired("Kein Token und keine GARMIN_EMAIL/GARMIN_PASSWORD gesetzt.")
            if login_with_credentials(email, password) == "mfa":
                submit_mfa(input("Garmin 2FA-Code: "))
        garmin = get_garmin_client()
        result = {"date": target_date.isoformat(), "health": fetch_health_data(garmin, target_date),
                  "workouts": fetch_workouts(garmin, target_date), "source": "garmin"}
        print(json.dumps({"status": "ok", "data": result}, ensure_ascii=False, default=str))
    except GarminError as e:
        print(json.dumps({"status": "error", "code": e.code, "message": str(e)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
