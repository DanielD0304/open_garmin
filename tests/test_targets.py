from db.targets import bmr, compute_targets

PROFILE = {"sex": "m", "age": 22, "heightCm": 180, "weightKg": 75, "activity": 1.2,
           "goal": "muscle", "strengthDays": 4, "cardioDays": 0}
TODAY = "2026-10-08"


def test_bmr_mifflin_and_katch():
    assert round(bmr(PROFILE)) == 1770                       # 750 + 1125 - 110 + 5
    assert round(bmr({**PROFILE, "bodyFat": 20})) == 1666    # 370 + 21.6 * 60
    assert round(bmr({**PROFILE, "sex": "f"})) == 1604


def test_without_garmin_uses_profile_estimate():
    t = compute_targets(PROFILE, None, TODAY, TODAY)
    assert t["source"] == "schaetzung"
    assert t["tdee"] == round(1770 * 1.4)                    # 1.2 + 4 × 0.05
    assert t["kcal"] == t["tdee"] + 250


def test_garmin_past_day_uses_measured_activity():
    t = compute_targets(PROFILE, 640, "2026-10-07", TODAY)
    assert t["source"] == "garmin"
    assert t["kcal"] == 1770 + 640 + 250
    assert [s["label"] for s in t["steps"]] == ["Grundumsatz", "Garmin aktiv", "Ziel: Muskelaufbau"]


def test_today_morning_keeps_everyday_baseline_until_garmin_exceeds_it():
    morning = compute_targets(PROFILE, 100, TODAY, TODAY)
    assert morning["source"] == "garmin-basis"
    assert morning["tdee"] == round(1770 * 1.2)
    after_training = compute_targets(PROFILE, 900, TODAY, TODAY)
    assert after_training["source"] == "garmin"
    assert after_training["kcal"] == 1770 + 900 + 250


def test_use_garmin_can_be_disabled():
    t = compute_targets({**PROFILE, "useGarmin": False}, 900, "2026-10-07", TODAY)
    assert t["source"] == "schaetzung"


def test_deficit_never_below_bmr():
    t = compute_targets({**PROFILE, "goal": "lose", "activity": 1.0, "strengthDays": 0}, None, TODAY, TODAY)
    assert t["kcal"] == round(bmr(PROFILE))


def test_macros_add_up_and_carbs_rise_with_activity():
    rest = compute_targets(PROFILE, 300, "2026-10-07", TODAY)
    training = compute_targets(PROFILE, 1000, "2026-10-07", TODAY)
    for t in (rest, training):
        assert abs(t["protein"] * 4 + t["carbs"] * 4 + t["fat"] * 9 - t["kcal"]) < 12
    assert training["protein"] == rest["protein"] == 150     # 2,0 g/kg beim Muskelaufbau
    assert training["carbs"] > rest["carbs"]


def test_protein_uses_lean_mass_when_body_fat_high():
    t = compute_targets({**PROFILE, "weightKg": 110, "bodyFat": 35, "goal": "lose"}, None, TODAY, TODAY)
    assert t["protein"] == round(110 * 0.65 * 1.2 * 2.0)
