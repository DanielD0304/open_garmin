"""
FastAPI Server – ersetzt http_server.py + n8n-Proxy.

Importiert DB-Funktionen direkt aus models.py (kein subprocess).
Serviert das Frontend als statische Dateien.

Starten: python -m db.server
Zugang:  http://localhost:8765/
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Optional
from urllib import request as urllib_request, error as urllib_error

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Pfade ────────────────────────────────────────────────────────

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
ENV_FILE = ROOT_DIR / ".env"

# Garmin-Modul importierbar machen
sys.path.insert(0, str(ROOT_DIR))


# ── .env laden ───────────────────────────────────────────────────

def load_project_env() -> None:
    """Laedt .env-Datei ins os.environ."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


load_project_env()


# ── DB Models importieren ────────────────────────────────────────

from db import models  # noqa: E402
from db.ai_client import generate_ai_report, get_model  # noqa: E402


# ── Pydantic Request Models ─────────────────────────────────────

class AddFoodRequest(BaseModel):
    date: Optional[str] = None
    meal_label: str = "snack"
    food_name: str
    amount_g: Optional[float] = None
    calories: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    fiber_g: float = 0


class DeleteFoodRequest(BaseModel):
    id: int


class AddHealthRequest(BaseModel):
    date: Optional[str] = None
    hrv_avg: Optional[float] = None
    hrv_status: Optional[str] = None
    sleep_score: Optional[int] = None
    sleep_hours: Optional[float] = None
    resting_hr: Optional[int] = None
    body_battery_high: Optional[int] = None
    body_battery_low: Optional[int] = None
    stress_avg: Optional[int] = None
    steps: Optional[int] = None
    active_calories: Optional[int] = None
    source: str = "manual"


class GarminSyncRequest(BaseModel):
    date: Optional[str] = None


# ── App Lifecycle ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/Shutdown: DB-Verbindung verwalten."""
    # Startup: Verbindung wird lazy bei erstem Zugriff erstellt
    yield
    # Shutdown: Verbindung schliessen
    models.close_connection()


# ── FastAPI App ──────────────────────────────────────────────────

app = FastAPI(
    title="AI Athletik-Coach API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── API-Wrapper (konsistente JSON-Responses) ─────────────────────

def ok_response(data: dict) -> JSONResponse:
    return JSONResponse({"status": "ok", "data": data})


def error_response(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"status": "error", "message": message}, status_code=status)


# ── Healthcheck ──────────────────────────────────────────────────

@app.get("/api/healthz")
async def healthcheck():
    return {"status": "ok", "message": "AI Athletik-Coach API is running", "version": "2.0.0"}


# ── Nutrition Endpoints ──────────────────────────────────────────

@app.post("/api/nutrition/add")
async def nutrition_add(req: AddFoodRequest):
    try:
        result = models.add_food(
            food_name=req.food_name,
            date=req.date,
            meal_label=req.meal_label,
            amount_g=req.amount_g,
            calories=req.calories,
            protein_g=req.protein_g,
            carbs_g=req.carbs_g,
            fat_g=req.fat_g,
            fiber_g=req.fiber_g,
        )
        return ok_response(result)
    except Exception as e:
        return error_response(f"add_food fehlgeschlagen: {e}", 500)


@app.post("/api/nutrition/delete")
async def nutrition_delete(req: DeleteFoodRequest):
    try:
        result = models.delete_food(req.id)
        return ok_response(result)
    except Exception as e:
        return error_response(f"delete_food fehlgeschlagen: {e}", 500)


@app.get("/api/nutrition/today")
async def nutrition_today(date: Optional[str] = Query(None)):
    try:
        result = models.get_food_log(date)
        return ok_response(result)
    except Exception as e:
        return error_response(f"get_food_log fehlgeschlagen: {e}", 500)


# ── Health Endpoints ─────────────────────────────────────────────

@app.post("/api/health/manual")
async def health_manual(req: AddHealthRequest):
    try:
        result = models.add_health(
            date=req.date,
            hrv_avg=req.hrv_avg,
            hrv_status=req.hrv_status,
            sleep_score=req.sleep_score,
            sleep_hours=req.sleep_hours,
            resting_hr=req.resting_hr,
            body_battery_high=req.body_battery_high,
            body_battery_low=req.body_battery_low,
            stress_avg=req.stress_avg,
            steps=req.steps,
            active_calories=req.active_calories,
            source=req.source,
        )
        return ok_response(result)
    except Exception as e:
        return error_response(f"add_health fehlgeschlagen: {e}", 500)


@app.get("/api/health/today")
async def health_today(date: Optional[str] = Query(None)):
    try:
        result = models.get_health(date)
        return ok_response(result)
    except Exception as e:
        return error_response(f"get_health fehlgeschlagen: {e}", 500)


# ── Garmin Sync ──────────────────────────────────────────────────

@app.post("/api/garmin/sync")
async def garmin_sync(req: GarminSyncRequest):
    """Holt Daten von Garmin Connect und speichert sie direkt in die DB."""
    target_date_str = req.date or date.today().isoformat()

    try:
        target_date = date.fromisoformat(target_date_str)
    except ValueError:
        return error_response(f"Ungueltiges Datum: {target_date_str}")

    # Garmin-Modul importieren (lazy, da es garminconnect braucht)
    try:
        from garmin.fetch_garmin import (
            load_env as garmin_load_env,
            get_garmin_client,
            fetch_health_data,
            fetch_workouts,
        )
    except ImportError as e:
        return error_response(f"Garmin-Modul nicht verfuegbar: {e}", 500)

    # Garmin-Daten abrufen
    try:
        garmin_load_env()
        client = get_garmin_client()
    except SystemExit:
        # fetch_garmin.py ruft sys.exit() bei Fehlern auf
        return JSONResponse({
            "status": "error",
            "code": "garmin_auth_failed",
            "message": "Garmin-Login fehlgeschlagen. Bitte manuell eingeben.",
        })
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "code": "garmin_error",
            "message": str(e),
        })

    try:
        health_data = fetch_health_data(client, target_date)
        workout_data = fetch_workouts(client, target_date)
    except Exception as e:
        return error_response(f"Garmin-Daten konnten nicht abgerufen werden: {e}", 500)

    # Health in DB speichern
    try:
        models.add_health(
            date=target_date_str,
            source="garmin",
            hrv_avg=health_data.get("hrv_avg"),
            hrv_status=health_data.get("hrv_status"),
            sleep_score=health_data.get("sleep_score"),
            sleep_hours=health_data.get("sleep_hours"),
            resting_hr=health_data.get("resting_hr"),
            body_battery_high=health_data.get("body_battery_high"),
            body_battery_low=health_data.get("body_battery_low"),
            stress_avg=health_data.get("stress_avg"),
            steps=health_data.get("steps"),
            active_calories=health_data.get("active_calories"),
        )
    except Exception as e:
        return error_response(f"Health-Daten speichern fehlgeschlagen: {e}", 500)

    # Workouts in DB speichern
    for w in workout_data:
        try:
            models.add_workout(
                date=target_date_str,
                activity_type=w.get("activity_type"),
                duration_min=w.get("duration_min"),
                distance_km=w.get("distance_km"),
                avg_hr=w.get("avg_hr"),
                max_hr=w.get("max_hr"),
                calories_burned=w.get("calories_burned"),
                training_load=w.get("training_load"),
            )
        except Exception:
            pass  # Einzelne Workout-Fehler nicht kritisch

    return ok_response({
        "date": target_date_str,
        "health": health_data,
        "workouts": workout_data,
        "source": "garmin",
    })


# ── History / Summary ────────────────────────────────────────────

@app.get("/api/history/summary")
async def history_summary(days: int = Query(7, ge=1, le=365)):
    try:
        result = models.get_summary(days)
        return ok_response(result)
    except Exception as e:
        return error_response(f"get_summary fehlgeschlagen: {e}", 500)


# ── Charts / Daily Overview ──────────────────────────────────────

@app.get("/api/charts/daily-overview")
async def charts_daily_overview(days: int = Query(14, ge=1, le=365)):
    try:
        result = models.get_daily_overview(days)
        return ok_response(result)
    except Exception as e:
        return error_response(f"get_daily_overview fehlgeschlagen: {e}", 500)


# ── Food Search (OpenFoodFacts) ──────────────────────────────────

def _map_off_product(product: dict) -> dict:
    """Maps an OpenFoodFacts product dict to our schema."""
    nut = product.get("nutriments") or {}
    return {
        "food_name": product.get("product_name") or "Unknown",
        "brand": product.get("brands") or "",
        "calories": round(nut.get("energy-kcal_100g") or nut.get("energy-kcal") or 0, 1),
        "protein_g": round(nut.get("proteins_100g") or nut.get("proteins") or 0, 1),
        "carbs_g": round(nut.get("carbohydrates_100g") or nut.get("carbohydrates") or 0, 1),
        "fat_g": round(nut.get("fat_100g") or nut.get("fat") or 0, 1),
        "fiber_g": round(nut.get("fiber_100g") or nut.get("fiber") or 0, 1),
        "barcode": product.get("code") or "",
        "image_url": product.get("image_small_url") or "",
    }


@app.get("/api/food/search")
async def food_search(q: str = Query(..., min_length=1)):
    """Search OpenFoodFacts for food products."""
    from urllib.parse import quote
    url = (
        f"https://world.openfoodfacts.org/cgi/search.pl"
        f"?search_terms={quote(q)}"
        f"&search_simple=1&action=process&json=1&page_size=8"
        f"&fields=product_name,brands,nutriments,code,image_small_url"
    )
    try:
        req = urllib_request.Request(url, headers={"User-Agent": "OpenGarmin/1.0"})
        with urllib_request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib_error.URLError, TimeoutError, ValueError) as e:
        return error_response(f"OpenFoodFacts search failed: {e}", 502)

    products = data.get("products") or []
    results = [_map_off_product(p) for p in products if p.get("product_name")]
    return ok_response(results)


@app.get("/api/food/barcode/{barcode}")
async def food_barcode(barcode: str):
    """Look up a specific barcode on OpenFoodFacts."""
    url = (
        f"https://world.openfoodfacts.org/api/v2/product/{barcode}"
        f"?fields=product_name,brands,nutriments,code,image_small_url"
    )
    try:
        req = urllib_request.Request(url, headers={"User-Agent": "OpenGarmin/1.0"})
        with urllib_request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib_error.URLError, TimeoutError, ValueError) as e:
        return error_response(f"OpenFoodFacts lookup failed: {e}", 502)

    product = data.get("product")
    if not product or data.get("status") == 0:
        return error_response("Product not found", 404)

    return ok_response(_map_off_product(product))


# ── Garmin Status ────────────────────────────────────────────────

@app.get("/api/garmin/status")
async def garmin_status():
    """Checks if a Garmin session exists and returns sync status."""
    session_dir = ROOT_DIR / "garmin" / ".garmin_session"
    session_exists = session_dir.exists() and any(session_dir.iterdir()) if session_dir.exists() else False

    # Get the latest synced date from DB
    last_sync_date = None
    try:
        conn = models.get_connection()
        row = conn.execute(
            "SELECT date FROM daily_health_metrics WHERE source = 'garmin' ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if row:
            last_sync_date = dict(row)["date"]
    except Exception:
        pass

    return ok_response({
        "status": "connected" if session_exists else "disconnected",
        "session_exists": session_exists,
        "last_sync_date": last_sync_date,
    })


# ── AI Report ────────────────────────────────────────────────────

@app.get("/api/report/generate")
async def report_generate():
    """Generiert den AI Coaching Report (Cloud-API mit Fallback)."""
    try:
        coaching_data = models.get_coaching_context(7)
    except Exception as e:
        return error_response(f"Zusammenfassung fehlgeschlagen: {e}", 500)

    context = build_report_context(coaching_data)
    report, ai_error = generate_ai_report(context)

    if report:
        return ok_response({
            "report": report,
            "mode": "api",
            "model": get_model(),
        })

    return ok_response({
        "report": build_fallback_report(coaching_data),
        "mode": "fallback",
        "model": None,
        "ai_error": ai_error,
    })


# ── Report-Kontext ───────────────────────────────────────────────

def build_report_context(coaching_data: dict) -> str:
    """Baut den Kontext-Text fuer das Modell auf (enriched with nutrition + trends)."""
    lines = ["=== ATHLETIK-DATEN DER LETZTEN 7 TAGE ===", ""]

    avg = coaching_data.get("health_averages") or {}
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

    health_daily = coaching_data.get("health_daily") or []
    if health_daily:
        lines.append("--- TAEGLICHE HEALTH-DATEN ---")
        for day in health_daily:
            lines.append(
                f"{day.get('date')}: HRV={day.get('hrv_avg') or '-'} "
                f"Sleep={day.get('sleep_score') or '-'} Puls={day.get('resting_hr') or '-'} "
                f"Stress={day.get('stress_avg') or '-'} Schritte={day.get('steps') or '-'}"
            )
        lines.append("")

    workouts = coaching_data.get("workouts") or []
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

    workout_summary = coaching_data.get("workout_summary") or {}
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
        lines.append("")

    # ── Nutrition data ───────────────────────────────────────────
    nutrition_daily = coaching_data.get("nutrition_daily") or []
    if nutrition_daily:
        lines.append("--- ERNAEHRUNG PRO TAG ---")
        for nd in nutrition_daily:
            lines.append(
                f"{nd.get('date')}: {nd.get('total_calories', 0):.0f} kcal | "
                f"P={nd.get('total_protein_g', 0):.0f}g "
                f"C={nd.get('total_carbs_g', 0):.0f}g "
                f"F={nd.get('total_fat_g', 0):.0f}g | "
                f"{nd.get('meal_count', 0)} Mahlzeiten"
            )
        lines.append("")

    # ── Trends ───────────────────────────────────────────────────
    trends = coaching_data.get("trends") or {}
    if trends:
        trend_labels = {"rising": "steigend", "falling": "fallend", "stable": "stabil"}
        lines.append("--- TRENDS ---")
        lines.append(f"HRV-Trend: {trend_labels.get(trends.get('hrv_trend', ''), 'stabil')}")
        lines.append(f"Schlaf-Trend: {trend_labels.get(trends.get('sleep_trend', ''), 'stabil')}")
        lines.append(f"Stress-Trend: {trend_labels.get(trends.get('stress_trend', ''), 'stabil')}")
        lines.append("")

    # ── Correlations ─────────────────────────────────────────────
    correlations = coaching_data.get("correlations") or []
    if correlations:
        lines.append("--- ERKANNTE MUSTER ---")
        for c in correlations:
            lines.append(f"- {c}")
        lines.append("")

    return "\n".join(lines)


def build_fallback_report(summary_data: dict) -> str:
    """Regel-basierter Fallback-Report wenn die AI-API nicht verfuegbar ist."""
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
        bullets.append("Schlafscore ist eher mittel. Heute besser frueh runterfahren und Schlaf priorisieren.")
    if hrv is not None and hrv < 50:
        bullets.append("HRV ist eher niedrig. Belastung lieber moderat halten und keine harte Einheit erzwingen.")
    if stress is not None and stress >= 50:
        bullets.append("Stress ist erhoeht. Fokus auf Erholung, Spaziergaenge und lockere Bewegung.")
    if resting_hr is not None and resting_hr >= 55:
        bullets.append("Ruhepuls liegt eher hoch. Das spricht fuer eine vorsichtige Trainingssteuerung.")
    if steps is not None and steps < 7000:
        bullets.append("Alltagsbewegung ist noch ausbaufaehig. Mehr lockere Schritte wuerden helfen.")
    if total_workouts == 0:
        bullets.append("Diese Woche gab es noch keine Workouts. Ein lockerer Einstieg waere sinnvoll.")

    if not bullets:
        bullets.append("Die Werte wirken insgesamt stabil. Trainingslast und Erholung passen grob zusammen.")

    lines = [
        "# AI Coaching Report", "",
        "## Kurzfazit",
        f"- HRV: {hrv if hrv is not None else 'n/a'} ms",
        f"- Schlafscore: {sleep_score if sleep_score is not None else 'n/a'}/100",
        f"- Schlafdauer: {sleep_hours if sleep_hours is not None else 'n/a'} h",
        f"- Ruhepuls: {resting_hr if resting_hr is not None else 'n/a'} bpm",
        f"- Stress: {stress if stress is not None else 'n/a'}/100",
        f"- Schritte/Tag: {round(steps) if steps is not None else 'n/a'}",
        "", "## Einordnung",
    ]
    lines.extend(f"- {bullet}" for bullet in bullets)
    lines.extend([
        "", "## Empfehlung fuer heute",
        "- Wenn du dich frisch fuehlst: lockere bis moderate Einheit.",
        "- Wenn Schlaf oder HRV schwach sind: Erholung, Zone-2 oder Spaziergang.",
        "- Naechster Fokus: Schlafrhythmus stabil halten und Alltagsbewegung sichern.",
    ])
    return "\n".join(lines)


# ── Legacy /run Endpoint (Abwaertskompatibilitaet) ───────────────

@app.post("/run")
async def legacy_run(payload: dict):
    """
    Abwaertskompatibel: Akzeptiert {action, params} wie der alte http_server.py.
    Leitet intern an die neuen Endpoints weiter.
    """
    action = payload.get("action")
    params = payload.get("params") or {}

    action_map = {
        "add_food": lambda p: models.add_food(**_remap_food(p)),
        "delete_food": lambda p: models.delete_food(p["id"]),
        "get_food_log": lambda p: models.get_food_log(p.get("date")),
        "add_health": lambda p: models.add_health(**p),
        "get_health": lambda p: models.get_health(p.get("date")),
        "add_workout": lambda p: models.add_workout(**p),
        "get_summary": lambda p: models.get_summary(p.get("days", 7)),
    }

    if action in action_map:
        try:
            result = action_map[action](params)
            return {"status": "ok", "data": result}
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

    if action == "generate_report":
        try:
            summary_data = models.get_summary(7)
            context = build_report_context(summary_data)
            report, error = generate_ai_report(context)
            if report:
                return {"status": "ok", "data": {"report": report, "mode": "api", "model": get_model()}}
            return {"status": "ok", "data": {"report": build_fallback_report(summary_data), "mode": "fallback", "ai_error": error}}
        except Exception as e:
            return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

    return JSONResponse({"status": "error", "message": f"Unknown action: {action}"}, status_code=400)


def _remap_food(params: dict) -> dict:
    """Mappt Legacy-Parameter-Namen auf models.add_food()."""
    return {
        "food_name": params.get("food_name", ""),
        "date": params.get("date"),
        "meal_label": params.get("meal_label", "snack"),
        "amount_g": params.get("amount_g"),
        "calories": params.get("calories", 0),
        "protein_g": params.get("protein_g", 0),
        "carbs_g": params.get("carbs_g", 0),
        "fat_g": params.get("fat_g", 0),
        "fiber_g": params.get("fiber_g", 0),
    }


# ── Static Files (Frontend) ─────────────────────────────────────

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")


# ── Main ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("OPEN_GARMIN_API_PORT", "8765"))
    print(f"AI Athletik-Coach API v2.0 starting on http://localhost:{port}")
    print(f"Frontend: http://localhost:{port}/")
    print(f"API Docs: http://localhost:{port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
