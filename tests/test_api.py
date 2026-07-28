"""Endpoints inkl. Token-Schutz, CORS-Defaults und Report-Fallback."""

import pytest
from fastapi.testclient import TestClient

from db import models, server


@pytest.fixture
def client(temp_db):
    """TestClient auf der Temp-DB. lifespan migriert sie beim Start erneut."""
    with TestClient(server.app) as c:
        yield c


# ── Basis ────────────────────────────────────────────────────────

def test_healthz(client):
    response = client.get("/api/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_nutrition_roundtrip(client):
    added = client.post("/api/nutrition/add", json={
        "food_name": "Haferflocken", "date": "2026-04-01",
        "meal_label": "breakfast", "calories": 350, "protein_g": 12,
    })
    assert added.status_code == 200
    entry_id = added.json()["data"]["id"]

    listed = client.get("/api/nutrition/today?date=2026-04-01").json()["data"]
    assert listed["totals"]["total_calories"] == pytest.approx(350)

    client.post("/api/nutrition/delete", json={"id": entry_id})
    after = client.get("/api/nutrition/today?date=2026-04-01").json()["data"]
    assert after["entries"] == []


def test_health_manual_and_readback(client):
    client.post("/api/health/manual", json={
        "date": "2026-04-02", "hrv_avg": 52, "sleep_score": 85, "source": "manual",
    })

    data = client.get("/api/health/today?date=2026-04-02").json()["data"]

    assert data["health"]["hrv_avg"] == 52
    assert data["health"]["sleep_score"] == 85


def test_history_summary_rejects_invalid_days(client):
    assert client.get("/api/history/summary?days=0").status_code == 422
    assert client.get("/api/history/summary?days=9999").status_code == 422


# ── Report ───────────────────────────────────────────────────────

def test_report_falls_back_without_api_key(client, no_ai_key):
    data = client.get("/api/report/generate").json()["data"]

    assert data["mode"] == "fallback"
    assert data["model"] is None
    assert "AI_API_KEY" in data["ai_error"]
    assert "# AI Coaching Report" in data["report"]


def test_report_uses_api_when_key_present(client, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL", "test-modell")
    monkeypatch.setattr(server, "generate_ai_report", lambda ctx: ("# Echt", None))

    data = client.get("/api/report/generate").json()["data"]

    assert data["mode"] == "api"
    assert data["report"] == "# Echt"
    assert data["model"] == "test-modell"


def test_fallback_report_mentions_missing_values(temp_db):
    report = server.build_fallback_report({})

    assert "# AI Coaching Report" in report
    assert "n/a" in report
    assert "Empfehlung" in report


def test_report_context_includes_all_sections(temp_db, monkeypatch):
    monkeypatch.setattr(models, "_today_iso", lambda: "2026-04-05")
    models.add_health(date="2026-04-05", hrv_avg=55, sleep_score=88,
                      stress_avg=30, steps=9000, source="garmin")
    models.add_workout(date="2026-04-05", activity_type="running", duration_min=45)
    models.add_food("Pasta", date="2026-04-05", calories=600, protein_g=20)

    context = server.build_report_context(models.get_coaching_context(7))

    assert "DURCHSCHNITTSWERTE" in context
    assert "WORKOUTS" in context
    assert "ERNAEHRUNG PRO TAG" in context
    assert "TRENDS" in context


# ── Sicherheit ───────────────────────────────────────────────────

def test_cors_defaults_to_localhost_only(monkeypatch):
    monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    origins = server.allowed_origins()

    assert "*" not in origins
    assert all("localhost" in o or "127.0.0.1" in o for o in origins)


def test_cors_can_be_configured(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://a.test, https://b.test")

    assert server.allowed_origins() == ["https://a.test", "https://b.test"]


def test_no_token_required_by_default(client, monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)

    assert client.get("/api/nutrition/today").status_code == 200


def test_token_blocks_unauthenticated_requests(client, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "geheim")

    assert client.get("/api/nutrition/today").status_code == 401
    assert client.post("/api/nutrition/add", json={"food_name": "x"}).status_code == 401


def test_token_accepts_bearer_and_api_key_header(client, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "geheim")

    assert client.get("/api/nutrition/today",
                      headers={"Authorization": "Bearer geheim"}).status_code == 200
    assert client.get("/api/nutrition/today",
                      headers={"X-API-Key": "geheim"}).status_code == 200


def test_token_rejects_wrong_value(client, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "geheim")

    assert client.get("/api/nutrition/today",
                      headers={"Authorization": "Bearer falsch"}).status_code == 401


def test_healthz_stays_public_with_token(client, monkeypatch):
    monkeypatch.setenv("API_TOKEN", "geheim")

    assert client.get("/api/healthz").status_code == 200
