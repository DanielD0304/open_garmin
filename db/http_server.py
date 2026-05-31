#!/usr/bin/env python3
"""Local HTTP wrapper for the open_garmin CLI scripts.

The n8n Docker image in this environment does not include the Execute Command
node, so workflows call this server instead and it shells out to the existing
Python scripts on the host.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request


ROOT_DIR = Path(__file__).resolve().parent.parent
VENV_PYTHON = ROOT_DIR / "venv" / "Scripts" / "python.exe"
PYTHON_EXE = str(VENV_PYTHON if VENV_PYTHON.exists() else Path(sys.executable))


def script_path(*parts: str) -> str:
    return str(ROOT_DIR.joinpath(*parts))


def build_python_command(*args: str) -> list[str]:
    return [PYTHON_EXE, *args]


def run_json_command(command: list[str]) -> tuple[dict, int]:
    completed = subprocess.run(
        command,
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )

    output = completed.stdout.strip()
    if not output:
        payload = {
            "status": "error",
            "message": completed.stderr.strip() or "Command produced no JSON output",
        }
        return payload, 500

    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        payload = {
            "status": "error",
            "message": "Command returned invalid JSON",
            "raw": output,
        }
        return payload, 500

    if completed.returncode != 0 or payload.get("status") == "error":
        return payload, 500

    return payload, 200


def add_flag(command: list[str], flag: str, value) -> None:
    if value is None or value == "":
        return
    command.extend([flag, str(value)])


def run_db_action(action: str, params: dict) -> tuple[dict, int]:
    if action == "add_food":
        command = build_python_command(script_path("db", "api.py"), "add_food")
        add_flag(command, "--date", params.get("date"))
        add_flag(command, "--meal-label", params.get("meal_label") or "snack")
        add_flag(command, "--food-name", params["food_name"])
        add_flag(command, "--amount-g", params.get("amount_g"))
        add_flag(command, "--calories", params.get("calories", 0))
        add_flag(command, "--protein-g", params.get("protein_g", 0))
        add_flag(command, "--carbs-g", params.get("carbs_g", 0))
        add_flag(command, "--fat-g", params.get("fat_g", 0))
        add_flag(command, "--fiber-g", params.get("fiber_g", 0))
        return run_json_command(command)

    if action == "delete_food":
        command = build_python_command(script_path("db", "api.py"), "delete_food")
        add_flag(command, "--id", params["id"])
        return run_json_command(command)

    if action == "get_food_log":
        command = build_python_command(script_path("db", "api.py"), "get_food_log")
        add_flag(command, "--date", params.get("date"))
        return run_json_command(command)

    if action == "add_health":
        command = build_python_command(script_path("db", "api.py"), "add_health")
        add_flag(command, "--date", params.get("date"))
        add_flag(command, "--hrv-avg", params.get("hrv_avg"))
        add_flag(command, "--hrv-status", params.get("hrv_status"))
        add_flag(command, "--sleep-score", params.get("sleep_score"))
        add_flag(command, "--sleep-hours", params.get("sleep_hours"))
        add_flag(command, "--resting-hr", params.get("resting_hr"))
        add_flag(command, "--body-battery-high", params.get("body_battery_high"))
        add_flag(command, "--body-battery-low", params.get("body_battery_low"))
        add_flag(command, "--stress-avg", params.get("stress_avg"))
        add_flag(command, "--steps", params.get("steps"))
        add_flag(command, "--active-calories", params.get("active_calories"))
        add_flag(command, "--source", params.get("source") or "manual")
        return run_json_command(command)

    if action == "get_health":
        command = build_python_command(script_path("db", "api.py"), "get_health")
        add_flag(command, "--date", params.get("date"))
        return run_json_command(command)

    if action == "add_workout":
        command = build_python_command(script_path("db", "api.py"), "add_workout")
        add_flag(command, "--date", params.get("date"))
        add_flag(command, "--activity-type", params.get("activity_type"))
        add_flag(command, "--duration-min", params.get("duration_min"))
        add_flag(command, "--distance-km", params.get("distance_km"))
        add_flag(command, "--avg-hr", params.get("avg_hr"))
        add_flag(command, "--max-hr", params.get("max_hr"))
        add_flag(command, "--calories-burned", params.get("calories_burned"))
        add_flag(command, "--training-load", params.get("training_load"))
        add_flag(command, "--notes", params.get("notes"))
        return run_json_command(command)

    if action == "get_summary":
        command = build_python_command(script_path("db", "api.py"), "get_summary")
        add_flag(command, "--days", params.get("days", 7))
        return run_json_command(command)

    if action == "fetch_garmin":
        command = build_python_command(script_path("garmin", "fetch_garmin.py"))
        add_flag(command, "--date", params.get("date"))
        return run_json_command(command)

    if action == "garmin_sync":
        fetch_payload, fetch_status = run_db_action("fetch_garmin", params)
        if fetch_status != 200 or fetch_payload.get("status") != "ok":
            return fetch_payload, fetch_status

        data = fetch_payload.get("data", {})
        health = data.get("health", {})
        save_payload, save_status = run_db_action(
            "add_health",
            {
                "date": data.get("date"),
                "source": "garmin",
                "hrv_avg": health.get("hrv_avg"),
                "hrv_status": health.get("hrv_status"),
                "sleep_score": health.get("sleep_score"),
                "sleep_hours": health.get("sleep_hours"),
                "resting_hr": health.get("resting_hr"),
                "body_battery_high": health.get("body_battery_high"),
                "body_battery_low": health.get("body_battery_low"),
                "stress_avg": health.get("stress_avg"),
                "steps": health.get("steps"),
                "active_calories": health.get("active_calories"),
            },
        )

        if save_status != 200 or save_payload.get("status") != "ok":
            return save_payload, save_status

        result = dict(fetch_payload)
        result["data"] = {
            **data,
            "saved_health": save_payload.get("data"),
        }
        return result, 200

    if action == "generate_report":
        summary_payload, summary_status = run_db_action("get_summary", {"days": 7})
        if summary_status != 200 or summary_payload.get("status") != "ok":
            return summary_payload, summary_status

        report_data = summary_payload.get("data", {})
        context = build_report_context(report_data)
        ollama_report = generate_ollama_report(context)

        if ollama_report:
            return {
                "status": "ok",
                "data": {
                    "report": ollama_report,
                    "mode": "ollama",
                    "model": os.environ.get("OLLAMA_MODEL", "gemma2"),
                },
            }, 200

        return {
            "status": "ok",
            "data": {
                "report": build_fallback_report(report_data),
                "mode": "fallback",
                "model": None,
            },
        }, 200

    return {"status": "error", "message": f"Unknown action: {action}"}, 400


def build_report_context(summary_data: dict) -> str:
    lines = ["=== ATHLETIK-DATEN DER LETZTEN 7 TAGE ===", ""]

    avg = summary_data.get("health_averages") or {}
    if avg:
        lines.append("--- DURCHSCHNITTSWERTE ---")
        if avg.get("avg_hrv") is not None:
            lines.append(f"HRV: {avg['avg_hrv']} ms")
        if avg.get("avg_sleep_score") is not None:
            lines.append(f"Sleep Score: {avg['avg_sleep_score']}/100")
        if avg.get("avg_sleep_hours") is not None:
            lines.append(f"Schlafdauer: {avg['avg_sleep_hours']} h")
        if avg.get("avg_resting_hr") is not None:
            lines.append(f"Ruhepuls: {avg['avg_resting_hr']} bpm")
        if avg.get("avg_stress") is not None:
            lines.append(f"Stress-Level: {avg['avg_stress']}/100")
        if avg.get("avg_steps") is not None:
            lines.append(f"Schritte/Tag: {round(avg['avg_steps'])}")
        lines.append("")

    health_daily = summary_data.get("health_daily") or []
    if health_daily:
        lines.append("--- TAEGLICHE HEALTH-DATEN ---")
        for day in health_daily:
            lines.append(
                f"{day.get('date')}: HRV={day.get('hrv_avg') or '-'} "
                f"Sleep={day.get('sleep_score') or '-'} Puls={day.get('resting_hr') or '-'} "
                f"Stress={day.get('stress_avg') or '-'} Schritte={day.get('steps') or '-'}"
            )
        lines.append("")

    workouts = summary_data.get("workouts") or []
    if workouts:
        lines.append("--- WORKOUTS ---")
        for workout in workouts:
            lines.append(
                f"{workout.get('date')}: {workout.get('activity_type') or 'Workout'} | "
                f"{workout.get('duration_min') or '-'} min | {workout.get('distance_km') or '-'} km | "
                f"HR {workout.get('avg_hr') or '-'}/{workout.get('max_hr') or '-'} | "
                f"{workout.get('calories_burned') or '-'} kcal | Load: {workout.get('training_load') or '-'}"
            )
        lines.append("")

    workout_summary = summary_data.get("workout_summary") or {}
    if workout_summary:
        lines.append("--- WOCHEN-ZUSAMMENFASSUNG ---")
        total_workouts = workout_summary.get("total_workouts") or 0
        total_duration = workout_summary.get("total_duration_min") or 0
        total_calories = workout_summary.get("total_calories_burned") or 0
        avg_hr = workout_summary.get("avg_heart_rate") or 0
        lines.append(
            f"Workouts: {total_workouts} | Dauer: {total_duration} min | "
            f"Kalorien: {total_calories} | Avg HR: {round(avg_hr)}"
        )

    return "\n".join(lines)


def generate_ollama_report(context: str) -> str | None:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.environ.get("OLLAMA_MODEL", "gemma2")
    payload = {
        "model": model,
        "prompt": context,
        "system": (
            "Du bist ein erfahrener Athletik- und Erholungs-Coach. "
            "Analysiere die folgenden Trainings- und Gesundheitsdaten und gib "
            "einen kurzen, praxisnahen Coaching-Report auf Deutsch. "
            "Beruecksichtige HRV-Trends, Schlafqualitaet, Stresslevel und Trainingsbelastung. "
            "Gib konkrete Empfehlungen fuer Training, Erholung und Schlaf. "
            "Halte den Report unter 500 Woertern. Formatiere mit Markdown-Ueberschriften und Aufzaehlungen."
        ),
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 1024},
    }

    request = urllib_request.Request(
        f"{base_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib_request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except (urllib_error.URLError, TimeoutError, ValueError):
        return None

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None

    report = parsed.get("response")
    return report.strip() if isinstance(report, str) and report.strip() else None


def build_fallback_report(summary_data: dict) -> str:
    avg = summary_data.get("health_averages") or {}
    workouts = summary_data.get("workouts") or []
    workout_summary = summary_data.get("workout_summary") or {}

    hrv = avg.get("avg_hrv")
    sleep_score = avg.get("avg_sleep_score")
    sleep_hours = avg.get("avg_sleep_hours")
    resting_hr = avg.get("avg_resting_hr")
    stress = avg.get("avg_stress")
    steps = avg.get("avg_steps")
    total_workouts = workout_summary.get("total_workouts") or len(workouts)

    bullets = []
    if sleep_score is not None and sleep_score < 75:
        bullets.append("Schlafscore ist eher mittel. Heute besser früh runterfahren und Schlaf priorisieren.")
    if hrv is not None and hrv < 50:
        bullets.append("HRV ist eher niedrig. Belastung lieber moderat halten und keine harte Einheit erzwingen.")
    if stress is not None and stress >= 50:
        bullets.append("Stress ist erhöht. Fokus auf Erholung, Spaziergänge und lockere Bewegung.")
    if resting_hr is not None and resting_hr >= 55:
        bullets.append("Ruhepuls liegt eher hoch. Das spricht für eine vorsichtige Trainingssteuerung.")
    if steps is not None and steps < 7000:
        bullets.append("Alltagsbewegung ist noch ausbaufähig. Mehr lockere Schritte würden helfen.")
    if total_workouts == 0:
        bullets.append("Diese Woche gab es noch keine Workouts. Ein lockerer Einstieg wäre sinnvoll.")

    if not bullets:
        bullets.append("Die Werte wirken insgesamt stabil. Trainingslast und Erholung passen grob zusammen.")

    lines = [
        "# AI Coaching Report",
        "",
        "## Kurzfazit",
        f"- HRV: {hrv if hrv is not None else 'n/a'} ms",
        f"- Schlafscore: {sleep_score if sleep_score is not None else 'n/a'}/100",
        f"- Schlafdauer: {sleep_hours if sleep_hours is not None else 'n/a'} h",
        f"- Ruhepuls: {resting_hr if resting_hr is not None else 'n/a'} bpm",
        f"- Stress: {stress if stress is not None else 'n/a'}/100",
        f"- Schritte/Tag: {round(steps) if steps is not None else 'n/a'}",
        "",
        "## Einordnung",
    ]
    lines.extend(f"- {bullet}" for bullet in bullets)
    lines.extend([
        "",
        "## Empfehlung für heute",
        "- Wenn du dich frisch fühlst: lockere bis moderate Einheit.",
        "- Wenn Schlaf oder HRV schwach sind: Erholung, Zone-2 oder Spaziergang.",
        "- Nächster Fokus: Schlafrhythmus stabil halten und Alltagsbewegung sichern.",
    ])
    return "\n".join(lines)


class RequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path in {"/", "/healthz"}:
            self._send_json({"status": "ok", "message": "open_garmin API server is running"})
            return
        self._send_json({"status": "error", "message": "Not found"}, 404)

    def do_POST(self) -> None:
        if self.path != "/run":
            self._send_json({"status": "error", "message": "Not found"}, 404)
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            self._send_json({"status": "error", "message": "Invalid JSON body"}, 400)
            return

        action = payload.get("action")
        params = payload.get("params") or {}
        if not action:
            self._send_json({"status": "error", "message": "Missing action"}, 400)
            return

        response, status = run_db_action(action, params)
        self._send_json(response, status)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    port = int(os.environ.get("OPEN_GARMIN_API_PORT", "8765"))
    host = os.environ.get("OPEN_GARMIN_API_HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), RequestHandler)
    print(f"open_garmin API server listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()