"""DB-Funktionen: Ernaehrung, Health-Upsert, Summary, Trends, Rohdaten."""

import pytest

from db import models


# ── Nutrition ────────────────────────────────────────────────────

def test_add_food_and_totals(temp_db):
    models.add_food("Skyr", date="2026-03-01", meal_label="breakfast",
                    calories=85, protein_g=15, carbs_g=4, fat_g=0.2)
    models.add_food("Banane", date="2026-03-01", meal_label="snack",
                    calories=90, protein_g=1, carbs_g=23, fat_g=0.3)

    log = models.get_food_log("2026-03-01")

    assert len(log["entries"]) == 2
    assert log["totals"]["total_calories"] == pytest.approx(175)
    assert log["totals"]["total_protein_g"] == pytest.approx(16)
    assert log["totals"]["meal_count"] == 2


def test_food_log_is_scoped_to_date(temp_db):
    models.add_food("Heute", date="2026-03-02", calories=100)
    models.add_food("Gestern", date="2026-03-01", calories=200)

    assert models.get_food_log("2026-03-02")["totals"]["total_calories"] == pytest.approx(100)


def test_empty_day_returns_zero_totals(temp_db):
    log = models.get_food_log("2026-03-09")

    assert log["entries"] == []
    assert log["totals"]["total_calories"] == 0
    assert log["totals"]["meal_count"] == 0


def test_delete_food(temp_db):
    entry = models.add_food("Fehler", date="2026-03-03", calories=500)
    models.delete_food(entry["id"])

    assert models.get_food_log("2026-03-03")["entries"] == []


# ── Health Upsert ────────────────────────────────────────────────

def test_add_health_upserts_by_date(temp_db):
    models.add_health(date="2026-03-04", hrv_avg=50, sleep_score=80, source="garmin")
    models.add_health(date="2026-03-04", hrv_avg=60, source="manual")

    health = models.get_health("2026-03-04")["health"]

    assert health["hrv_avg"] == 60
    # sleep_score war im zweiten Aufruf None -> COALESCE behaelt den alten Wert
    assert health["sleep_score"] == 80
    assert health["source"] == "manual"


def test_add_health_rejects_unknown_source(temp_db):
    with pytest.raises(Exception):
        models.add_health(date="2026-03-05", hrv_avg=50, source="fitbit")


# ── Summary ──────────────────────────────────────────────────────

def test_summary_averages_and_workout_totals(temp_db, monkeypatch):
    monkeypatch.setattr(models, "_today_iso", lambda: "2026-03-10")

    models.add_health(date="2026-03-09", hrv_avg=40, sleep_score=70, source="garmin")
    models.add_health(date="2026-03-10", hrv_avg=60, sleep_score=90, source="garmin")
    models.add_workout(date="2026-03-10", activity_type="running",
                       duration_min=30, calories_burned=300, avg_hr=140)
    models.add_workout(date="2026-03-10", activity_type="cycling",
                       duration_min=60, calories_burned=500, avg_hr=120)

    summary = models.get_summary(7)

    assert summary["health_averages"]["avg_hrv"] == pytest.approx(50)
    assert summary["health_averages"]["avg_sleep_score"] == pytest.approx(80)
    assert summary["workout_summary"]["total_workouts"] == 2
    assert summary["workout_summary"]["total_duration_min"] == pytest.approx(90)
    assert summary["workout_summary"]["total_calories_burned"] == pytest.approx(800)
    assert summary["workout_summary"]["avg_heart_rate"] == pytest.approx(130)


def test_summary_window_excludes_older_days(temp_db, monkeypatch):
    monkeypatch.setattr(models, "_today_iso", lambda: "2026-03-10")

    models.add_health(date="2026-03-10", hrv_avg=60, source="garmin")
    models.add_health(date="2026-01-01", hrv_avg=10, source="garmin")

    dates = [d["date"] for d in models.get_summary(7)["health_daily"]]

    assert "2026-03-10" in dates
    assert "2026-01-01" not in dates


# ── Trends ───────────────────────────────────────────────────────

def test_linear_trend_detects_direction():
    assert models._linear_trend([40, 45, 50, 55, 60]) == "rising"
    assert models._linear_trend([60, 55, 50, 45, 40]) == "falling"
    assert models._linear_trend([50, 50, 50, 50]) == "stable"


def test_linear_trend_handles_sparse_data():
    assert models._linear_trend([]) == "stable"
    assert models._linear_trend([None, None]) == "stable"
    assert models._linear_trend([50]) == "stable"
    assert models._linear_trend([None, 50, None, 70]) == "rising"


def test_coaching_context_has_trends_and_nutrition(temp_db, monkeypatch):
    monkeypatch.setattr(models, "_today_iso", lambda: "2026-03-10")

    for offset, hrv in enumerate([40, 45, 50, 55, 60]):
        models.add_health(date=f"2026-03-{6 + offset:02d}", hrv_avg=hrv,
                          sleep_score=80, source="garmin")
    models.add_food("Reis", date="2026-03-10", calories=400)

    context = models.get_coaching_context(7)

    assert context["trends"]["hrv_trend"] == "rising"
    assert any(n["date"] == "2026-03-10" for n in context["nutrition_daily"])
    assert isinstance(context["correlations"], list)


# ── Garmin Rohdaten ──────────────────────────────────────────────

def test_raw_payload_roundtrip(temp_db):
    payload = {"hrvSummary": {"weeklyAvg": 55, "status": "BALANCED"}, "nested": [1, 2, 3]}
    models.save_raw_payload("2026-03-11", "hrv", payload)

    stored = models.get_raw_payloads("2026-03-11", "hrv")

    assert len(stored) == 1
    assert stored[0]["payload"] == payload
    assert stored[0]["kind"] == "hrv"


def test_raw_payload_filter_by_kind(temp_db):
    models.save_raw_payload("2026-03-12", "hrv", {"a": 1})
    models.save_raw_payload("2026-03-12", "sleep", {"b": 2})

    assert len(models.get_raw_payloads("2026-03-12")) == 2
    assert len(models.get_raw_payloads("2026-03-12", "sleep")) == 1


def test_raw_payload_survives_non_serialisable_values(temp_db):
    """default=str verhindert, dass ein exotischer Typ den ganzen Sync kippt."""
    from datetime import datetime

    models.save_raw_payload("2026-03-13", "stats", {"ts": datetime(2026, 3, 13, 8, 0)})

    assert models.get_raw_payloads("2026-03-13", "stats")[0]["payload"]["ts"].startswith("2026-03-13")
