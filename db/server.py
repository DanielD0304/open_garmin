"""
FastAPI-Backend der AI-Coach-Desktop-App.

Serviert das Frontend und die API. Wird normalerweise von app.py im
Programmfenster gestartet; zum Debuggen im Browser:
    python -m db.server   →  http://127.0.0.1:8765/
"""

from __future__ import annotations

import json
import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import date, timedelta
from typing import Optional

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from db import claude_client, mensa, models
from db.claude_client import ClaudeError
from db.init_db import init_database
from db.paths import FRONTEND_DIR
from db.targets import compute_targets
from garmin import fetch_garmin
from garmin.fetch_garmin import GarminError

log = logging.getLogger("ai_coach")


# ── Request-Modelle ──────────────────────────────────────────────

class AddFoodRequest(BaseModel):
    date: Optional[str] = None
    meal_label: str = "snack"
    food_name: str
    amount_g: Optional[float] = None
    amount_text: Optional[str] = None
    calories: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    fiber_g: float = 0
    sugar_g: Optional[float] = None
    satfat_g: Optional[float] = None
    salt_g: Optional[float] = None
    price_eur: Optional[float] = None
    source: Optional[str] = None
    notes: Optional[str] = None


class UpdateFoodRequest(BaseModel):
    id: int
    date: Optional[str] = None
    meal_label: Optional[str] = None
    food_name: Optional[str] = None
    amount_text: Optional[str] = None
    calories: Optional[float] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    sugar_g: Optional[float] = None
    fat_g: Optional[float] = None
    satfat_g: Optional[float] = None
    fiber_g: Optional[float] = None
    salt_g: Optional[float] = None
    price_eur: Optional[float] = None
    source: Optional[str] = None
    notes: Optional[str] = None


class DeleteFoodRequest(BaseModel):
    id: int


class FavoriteRequest(BaseModel):
    food_name: str
    amount_text: Optional[str] = None
    calories: Optional[float] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    sugar_g: Optional[float] = None
    fat_g: Optional[float] = None
    satfat_g: Optional[float] = None
    fiber_g: Optional[float] = None
    salt_g: Optional[float] = None
    price_eur: Optional[float] = None
    source: Optional[str] = None
    notes: Optional[str] = None


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


class GarminLoginRequest(BaseModel):
    email: str
    password: str


class GarminMfaRequest(BaseModel):
    code: str


class LookupRequest(BaseModel):
    text: str
    date: Optional[str] = None
    meal: Optional[str] = None
    answers: list[dict] = []
    research: Optional[str] = None


class AdviceRequest(BaseModel):
    date: Optional[str] = None


# ── App ──────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_database(verbose=False)
    threading.Thread(target=auto_sync_garmin, name="garmin-auto-sync", daemon=True).start()
    yield
    models.close_connection()


app = FastAPI(title="AI Coach", version="3.0.0", lifespan=lifespan)


def ok_response(data) -> JSONResponse:
    return JSONResponse({"status": "ok", "data": data})


def error_response(message: str, status: int = 400, code: str | None = None) -> JSONResponse:
    body = {"status": "error", "message": message}
    if code:
        body["code"] = code
    return JSONResponse(body, status_code=status)


def _day(value: str | None) -> str:
    return value or date.today().isoformat()


@app.get("/api/healthz")
async def healthcheck():
    return {"status": "ok", "message": "AI Coach API is running", "version": "3.0.0"}


# ── Ernaehrung ───────────────────────────────────────────────────

@app.post("/api/nutrition/add")
async def nutrition_add(req: AddFoodRequest):
    try:
        return ok_response(models.add_food(**req.model_dump()))
    except Exception as e:
        return error_response(f"add_food fehlgeschlagen: {e}", 500)


@app.post("/api/nutrition/update")
async def nutrition_update(req: UpdateFoodRequest):
    entry = models.update_food(req.id, **req.model_dump(exclude={"id"}, exclude_unset=True))
    return ok_response(entry) if entry else error_response("Eintrag nicht gefunden", 404)


@app.post("/api/nutrition/delete")
async def nutrition_delete(req: DeleteFoodRequest):
    return ok_response(models.delete_food(req.id))


@app.get("/api/nutrition/today")
async def nutrition_today(date: Optional[str] = Query(None)):
    return ok_response(models.get_food_log(date))


@app.get("/api/nutrition/range")
async def nutrition_range(start: str = Query(...), end: str = Query(...)):
    return ok_response({"entries": models.get_food_range(start, end)})


# ── Favoriten ────────────────────────────────────────────────────

@app.get("/api/favorites")
async def favorites_list():
    return ok_response({"favorites": models.list_favorites()})


@app.post("/api/favorites")
async def favorites_add(req: FavoriteRequest):
    return ok_response(models.add_favorite(**req.model_dump()))


@app.put("/api/favorites/{fav_id}")
async def favorites_update(fav_id: int, req: FavoriteRequest):
    fav = models.update_favorite(fav_id, **req.model_dump(exclude_unset=True))
    return ok_response(fav) if fav else error_response("Favorit nicht gefunden", 404)


@app.delete("/api/favorites/{fav_id}")
async def favorites_delete(fav_id: int):
    return ok_response(models.delete_favorite(fav_id))


# ── Profil & Tagesziele ──────────────────────────────────────────

@app.get("/api/profile")
async def profile_get():
    return ok_response(models.get_profile())


@app.put("/api/profile")
async def profile_put(payload: dict):
    return ok_response(models.save_profile(payload))


def targets_for(day: str) -> dict:
    health = models.get_health(day).get("health") or {}
    active = health.get("active_calories") if health.get("source") == "garmin" else None
    return compute_targets(models.get_profile(), active, day)


@app.get("/api/targets")
async def targets_get(date: Optional[str] = Query(None)):
    return ok_response(targets_for(_day(date)))


# ── Health ───────────────────────────────────────────────────────

@app.post("/api/health/manual")
async def health_manual(req: AddHealthRequest):
    return ok_response(models.add_health(**req.model_dump()))


@app.get("/api/health/today")
async def health_today(date: Optional[str] = Query(None)):
    return ok_response(models.get_health(date))


# ── Garmin ───────────────────────────────────────────────────────

def _garmin_error(e: GarminError) -> JSONResponse:
    return error_response(str(e), 401 if isinstance(e, fetch_garmin.GarminAuthRequired) else 502, e.code)


@app.get("/api/garmin/status")
async def garmin_status():
    return ok_response({"connected": fetch_garmin.is_connected()})


@app.post("/api/garmin/login")
def garmin_login(req: GarminLoginRequest):
    try:
        result = fetch_garmin.login_with_credentials(req.email.strip(), req.password)
    except GarminError as e:
        return _garmin_error(e)
    if result == "ok":
        threading.Thread(target=auto_sync_garmin, daemon=True).start()
    return ok_response({"connected": result == "ok", "mfa": result == "mfa"})


@app.post("/api/garmin/mfa")
def garmin_mfa(req: GarminMfaRequest):
    try:
        fetch_garmin.submit_mfa(req.code)
    except GarminError as e:
        return _garmin_error(e)
    threading.Thread(target=auto_sync_garmin, daemon=True).start()
    return ok_response({"connected": True})


@app.post("/api/garmin/logout")
async def garmin_logout():
    fetch_garmin.logout()
    return ok_response({"connected": False})


def sync_day(client, target: date) -> dict:
    health = fetch_garmin.fetch_health_data(client, target)
    workouts = fetch_garmin.fetch_workouts(client, target)
    models.add_health(date=target.isoformat(), source="garmin", **health)
    models.replace_workouts(target.isoformat(), workouts)
    return {"date": target.isoformat(), "health": health, "workouts": workouts, "source": "garmin"}


def import_body_profile(client) -> dict:
    garmin_profile = fetch_garmin.fetch_body_profile(client)
    updates = {k: v for k, v in garmin_profile.items() if k in models.DEFAULT_PROFILE and v not in (None, "")}
    return {"profile": models.save_profile(updates) if updates else models.get_profile(), "fromGarmin": garmin_profile}


@app.post("/api/garmin/sync")
def garmin_sync(req: GarminSyncRequest):
    try:
        target = date.fromisoformat(_day(req.date))
    except ValueError:
        return error_response(f"Ungueltiges Datum: {req.date}")
    try:
        client = fetch_garmin.get_garmin_client()
        result = sync_day(client, target)
        if models.get_profile().get("garminWeightSync"):
            import_body_profile(client)
    except GarminError as e:
        return _garmin_error(e)
    return ok_response(result)


@app.post("/api/garmin/import-profile")
def garmin_import_profile():
    try:
        return ok_response(import_body_profile(fetch_garmin.get_garmin_client()))
    except GarminError as e:
        return _garmin_error(e)


_sync_lock = threading.Lock()


def auto_sync_garmin(days: int = 7) -> None:
    """Beim Start: heute + gestern immer, aeltere Tage nur wenn noch keine Garmin-Daten da sind."""
    if not fetch_garmin.is_connected() or not _sync_lock.acquire(blocking=False):
        return
    try:
        client = fetch_garmin.get_garmin_client()
        today = date.today()
        have = models.synced_dates((today - timedelta(days=days - 1)).isoformat(), today.isoformat())
        for offset in range(days):
            target = today - timedelta(days=offset)
            if offset < 2 or target.isoformat() not in have:
                sync_day(client, target)
        if models.get_profile().get("garminWeightSync"):
            import_body_profile(client)
        log.info("Garmin-Auto-Sync abgeschlossen")
    except Exception as e:
        log.warning("Garmin-Auto-Sync fehlgeschlagen: %s", e)
    finally:
        _sync_lock.release()


# ── Claude (Claude-Abo ueber die Claude Code CLI) ────────────────
# Synchrone Endpoints: FastAPI fuehrt sie im Threadpool aus, der
# blockierende CLI-Aufruf haelt so den Server nicht an.

@app.get("/api/claude/status")
def claude_status():
    binary = claude_client.find_claude()
    return ok_response({"found": bool(binary), "path": binary})


def _num_or_none(value):
    try:
        return None if value is None or value == "" else float(value)
    except (TypeError, ValueError):
        return None


def _clean_item(raw: dict) -> dict:
    """Claude-Format → Spaltennamen der nutrition_log."""
    return {
        "food_name": str(raw.get("name") or "Unbenannt")[:200],
        "amount_text": str(raw.get("amount") or "")[:100],
        "calories": _num_or_none(raw.get("kcal")),
        "protein_g": _num_or_none(raw.get("protein")),
        "carbs_g": _num_or_none(raw.get("carbs")),
        "sugar_g": _num_or_none(raw.get("sugar")),
        "fat_g": _num_or_none(raw.get("fat")),
        "satfat_g": _num_or_none(raw.get("satfat")),
        "fiber_g": _num_or_none(raw.get("fiber")),
        "salt_g": _num_or_none(raw.get("salt")),
        "price_eur": _num_or_none(raw.get("price")),
        "source": str(raw.get("source") or "")[:500],
        "notes": str(raw.get("notes") or "")[:1000],
        "confidence": str(raw.get("confidence") or ""),
    }


@app.post("/api/claude/lookup")
def claude_lookup(req: LookupRequest):
    if not req.text.strip():
        return error_response("Bitte beschreibe, was du gegessen hast.")
    day = _day(req.date)
    menu = mensa.get_menu(req.text, day, models.get_profile()["priceGroup"])
    prompt = claude_client.lookup_prompt(
        req.text, day, req.meal, req.answers[:12], (req.research or "")[:6000], menu)
    try:
        text, usage = claude_client.run_claude(prompt, kind="lookup")
        result = claude_client.extract_json(text)
    except (ClaudeError, json.JSONDecodeError) as e:
        return error_response(str(e), 502)

    questions = [
        {"question": str(q["question"]), "options": [str(o) for o in (q.get("options") or [])][:6]}
        for q in (result.get("questions") or []) if isinstance(q, dict) and q.get("question")
    ][:3]
    if result.get("status") == "question" and questions:
        research = result.get("research") or ""
        return ok_response({
            "status": "question", "questions": questions, "comment": result.get("comment") or "",
            "research": research if isinstance(research, str) else json.dumps(research, ensure_ascii=False),
            "usage": usage,
        })
    return ok_response({
        "status": "ok", "items": [_clean_item(i) for i in result.get("items") or [] if isinstance(i, dict)],
        "comment": result.get("comment") or "", "usage": usage,
    })


@app.post("/api/claude/advice")
def claude_advice(req: AdviceRequest):
    day = _day(req.date)
    totals = models.get_food_log(day)["totals"]
    try:
        text, usage = claude_client.run_claude(
            claude_client.advice_prompt(day, targets_for(day), totals), kind="advice", timeout=180)
    except ClaudeError as e:
        return error_response(str(e), 502)
    return ok_response({"text": text, "usage": usage})


@app.get("/api/usage")
async def usage_get():
    return ok_response(models.get_claude_usage())


@app.post("/api/usage/refresh")
def usage_refresh():
    """Mini-Anfrage an Haiku ohne Tools, nur um den aktuellen Limit-Stand abzurufen."""
    try:
        _, usage = claude_client.run_claude("Antworte nur mit: ok", kind="limit-check",
                                            model="haiku", tools="", timeout=60)
    except ClaudeError as e:
        return error_response(str(e), 502)
    return ok_response(usage)


# ── Verlauf ──────────────────────────────────────────────────────

@app.get("/api/history/summary")
async def history_summary(days: int = Query(7, ge=1, le=365)):
    return ok_response(models.get_summary(days))


# ── Coach-Report (Claude) ────────────────────────────────────────

@app.get("/api/report/generate")
def report_generate():
    summary = models.get_summary(7)
    today = date.today().isoformat()
    prompt = claude_client.report_prompt(
        build_report_context(summary), build_nutrition_lines(7), targets_for(today))
    try:
        report, usage = claude_client.run_claude(prompt, kind="report", tools="", timeout=300)
    except ClaudeError as e:
        return error_response(str(e), 502)
    return ok_response({"report": report.strip(), "mode": "claude",
                        "model": usage["request"]["model"], "usage": usage})


def build_report_context(summary_data: dict) -> str:
    """Garmin-Daten der letzten 7 Tage als Text fuer den Report."""
    lines = ["=== TRAINING & ERHOLUNG, LETZTE 7 TAGE ===", ""]

    avg = summary_data.get("health_averages") or {}
    labels = [("avg_hrv", "HRV", "ms"), ("avg_sleep_score", "Sleep Score", "/100"),
              ("avg_sleep_hours", "Schlafdauer", "h"), ("avg_resting_hr", "Ruhepuls", "bpm"),
              ("avg_stress", "Stress-Level", "/100"), ("avg_steps", "Schritte/Tag", "")]
    values = [f"{label}: {round(avg[key]) if key == 'avg_steps' else avg[key]} {unit}".strip()
              for key, label, unit in labels if avg.get(key) is not None]
    if values:
        lines += ["--- DURCHSCHNITTSWERTE ---", *values, ""]

    health_daily = summary_data.get("health_daily") or []
    if health_daily:
        lines.append("--- TAEGLICHE HEALTH-DATEN ---")
        for day in health_daily:
            lines.append(
                f"{day.get('date')}: HRV={day.get('hrv_avg') or '-'} Sleep={day.get('sleep_score') or '-'} "
                f"Puls={day.get('resting_hr') or '-'} Stress={day.get('stress_avg') or '-'} "
                f"Schritte={day.get('steps') or '-'} aktive kcal={day.get('active_calories') or '-'}"
            )
        lines.append("")

    workouts = summary_data.get("workouts") or []
    if workouts:
        lines.append("--- WORKOUTS ---")
        for w in workouts:
            lines.append(
                f"{w.get('date')}: {w.get('activity_type') or 'Workout'} | {w.get('duration_min') or '-'} min | "
                f"{w.get('distance_km') or '-'} km | HR {w.get('avg_hr') or '-'}/{w.get('max_hr') or '-'} | "
                f"{w.get('calories_burned') or '-'} kcal | Load: {w.get('training_load') or '-'}"
            )
    return "\n".join(lines) if len(lines) > 2 else "Keine Garmin-Daten in den letzten 7 Tagen."


def build_nutrition_lines(days: int) -> str:
    """Tagessummen der Ernaehrung fuer den Report, jeweils mit Tagesziel."""
    end = date.today()
    start = end - timedelta(days=days - 1)
    per_day: dict[str, dict] = {}
    for e in models.get_food_range(start.isoformat(), end.isoformat()):
        d = per_day.setdefault(e["date"], {"kcal": 0, "protein": 0, "carbs": 0, "fat": 0, "price": 0, "n": 0})
        d["kcal"] += e.get("calories") or 0
        d["protein"] += e.get("protein_g") or 0
        d["carbs"] += e.get("carbs_g") or 0
        d["fat"] += e.get("fat_g") or 0
        d["price"] += e.get("price_eur") or 0
        d["n"] += 1
    lines = []
    for day, v in sorted(per_day.items()):
        t = targets_for(day)
        lines.append(
            f"{day}: {round(v['kcal'])}/{t['kcal']} kcal, Eiweiß {round(v['protein'])}/{t['protein']} g, "
            f"KH {round(v['carbs'])} g, Fett {round(v['fat'])} g, {v['n']} Einträge, {v['price']:.2f} €"
        )
    return "\n".join(lines)


# ── Frontend ─────────────────────────────────────────────────────

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("OPEN_GARMIN_API_PORT", "8765"))
    print(f"AI Coach API auf http://127.0.0.1:{port}/")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
