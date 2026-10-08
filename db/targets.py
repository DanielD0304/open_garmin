"""
Tagesbedarf aus Koerperprofil + gemessener Garmin-Aktivitaet.

Grundumsatz:  Katch-McArdle (mit Koerperfett) oder Mifflin-St Jeor.
Aktivitaet:   1. Garmin-aktive kcal des Tages (Schritte + Workouts, gemessen)
              2. ohne Garmin-Daten: Schaetzung aus Alltag + Trainingseinheiten im Profil
Ziel:         Zu-/Abschlag je nach Ziel, Untergrenze = Grundumsatz.
Makros:       Eiweiss je Ziel (g/kg), Fett 30 % (mind. 0,8 g/kg), Kohlenhydrate = Rest.
"""

from __future__ import annotations

from datetime import date as date_cls

GOALS = {
    "lose":     {"label": "Fett verlieren", "kcal": -500, "protein": 2.0},
    "recomp":   {"label": "Recomp",         "kcal": -250, "protein": 2.2},
    "maintain": {"label": "Gewicht halten", "kcal": 0,    "protein": 1.6},
    "muscle":   {"label": "Muskelaufbau",   "kcal": 250,  "protein": 2.0},
    "gain":     {"label": "Zunehmen",       "kcal": 500,  "protein": 1.8},
}


def _num(value, default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def bmr(profile: dict) -> float:
    weight, body_fat = _num(profile.get("weightKg"), 75), _num(profile.get("bodyFat"))
    if body_fat:
        return 370 + 21.6 * weight * (1 - body_fat / 100)
    return (10 * weight + 6.25 * _num(profile.get("heightCm"), 180) - 5 * _num(profile.get("age"), 25)
            + (-161 if profile.get("sex") == "f" else 5))


def estimated_pal(profile: dict) -> float:
    """Aktivitaetsfaktor ohne Garmin: Alltag + ~0,05 je Kraft- und ~0,06 je Ausdauereinheit pro Woche."""
    pal = (_num(profile.get("activity"), 1.2) + 0.05 * _num(profile.get("strengthDays"))
           + 0.06 * _num(profile.get("cardioDays")))
    return min(pal, 2.3)


def compute_targets(profile: dict, garmin_active_kcal: float | None = None,
                    day: str | None = None, today: str | None = None) -> dict:
    """Berechnet Tagesziele. garmin_active_kcal=None → keine Garmin-Daten fuer den Tag."""
    today = today or date_cls.today().isoformat()
    day = day or today
    weight = _num(profile.get("weightKg"), 75)
    body_fat = _num(profile.get("bodyFat"))
    base = bmr(profile)
    goal = GOALS.get(profile.get("goal"), GOALS["maintain"])
    everyday = _num(profile.get("activity"), 1.2)

    steps = [("Grundumsatz", round(base))]
    if garmin_active_kcal is not None and profile.get("useGarmin", True):
        active = _num(garmin_active_kcal)
        measured = base + active
        if day == today and measured < base * everyday:
            # Tag laeuft noch: mindestens die Alltagsbasis, Training hebt das Ziel spaeter an
            tdee, source = base * everyday, "garmin-basis"
            steps.append(("Alltag (Garmin bisher " + str(round(active)) + " kcal aktiv)", round(tdee - base)))
        else:
            tdee, source = measured, "garmin"
            steps.append(("Garmin aktiv", round(active)))
    else:
        pal = estimated_pal(profile)
        tdee, source = base * pal, "schaetzung"
        steps.append((f"Aktivität geschätzt (× {pal:.2f})", round(tdee - base)))

    kcal = max(tdee + goal["kcal"], base)
    goal_delta = kcal - tdee
    if goal_delta:
        steps.append((f"Ziel: {goal['label']}", round(goal_delta)))

    protein_per_kg = _num(profile.get("proteinPerKg")) or goal["protein"]
    if not _num(profile.get("proteinPerKg")) and _num(profile.get("strengthDays")) >= 2 and profile.get("goal") == "maintain":
        protein_per_kg = 1.8
    high_fat = body_fat and body_fat > (32 if profile.get("sex") == "f" else 25)
    protein_base = weight * (1 - body_fat / 100) * 1.2 if high_fat else weight
    protein = round(protein_base * protein_per_kg)
    fat = round(max(kcal * 0.3 / 9, weight * 0.8))
    carbs = max(0, round((kcal - protein * 4 - fat * 9) / 4))

    return {
        "date": day,
        "kcal": round(kcal),
        "protein": protein,
        "carbs": carbs,
        "fat": fat,
        "fiber": 30,
        "sugar": round(kcal * 0.1 / 4),
        "satfat": round(kcal * 0.1 / 9),
        "salt": 6,
        "budget": _num(profile.get("dailyBudget")),
        "bmr": round(base),
        "tdee": round(tdee),
        "goal": goal["label"],
        "goalDelta": round(goal_delta),
        "proteinPerKg": protein_per_kg,
        "source": source,
        "garminActive": None if garmin_active_kcal is None else round(_num(garmin_active_kcal)),
        "steps": [{"label": label, "kcal": value} for label, value in steps],
    }
