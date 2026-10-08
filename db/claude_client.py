"""
Claude-Anbindung ueber die Claude Code CLI (laeuft mit dem Claude-Abo, kein API-Key).

Die CLI wird im schlanken Modus gestartet (ohne Plugins, Skills, MCP-Server und
Claude-Code-Systemprompt). Das spart pro Anfrage ~80.000 Tokens. Claude darf nur
WebSearch/WebFetch benutzen. Jede Antwort enthaelt den Limit-Stand des Abos
(rate_limit_event), der zusammen mit dem Token-Verbrauch gespeichert wird.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from db import models

from db.paths import CLAUDE_WORKDIR as WORKDIR
SYSTEM_PROMPT = (
    "Du bist ein praeziser Ernaehrungs- und Trainings-Assistent in einer lokalen Tracking-App. "
    "Halte dich exakt an das verlangte Antwortformat."
)
WEEKDAYS = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


class ClaudeError(Exception):
    pass


def find_claude(profile: dict | None = None) -> str | None:
    """Sucht die Claude Code CLI: Profil/ENV, ~/.local/bin, PATH, Claude-Desktop-App."""
    profile = profile or models.get_profile()
    exe = "claude.exe" if sys.platform == "win32" else "claude"
    candidates = [os.environ.get("CLAUDE_PATH"), profile.get("claudePath"),
                  str(Path.home() / ".local" / "bin" / exe), shutil.which("claude")]
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata) / "Claude" / "claude-code"
        if base.is_dir():
            def version_key(p: Path):
                return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", p.name)]
            for version in sorted(base.iterdir(), key=version_key, reverse=True):
                candidates.extend(str(p) for p in version.glob("*/claude.exe"))
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return None


def run_claude(prompt: str, kind: str = "lookup", model: str | None = None,
               tools: str = "WebSearch,WebFetch", timeout: int = 240) -> tuple[str, dict]:
    """Fuehrt eine Claude-Anfrage aus. Gibt (Antworttext, Verbrauch) zurueck."""
    profile = models.get_profile()
    binary = find_claude(profile)
    if not binary:
        raise ClaudeError("Claude Code CLI nicht gefunden. Installieren: irm https://claude.ai/install.ps1 | iex")
    model = model or profile.get("claudeModel") or "sonnet"
    WORKDIR.mkdir(parents=True, exist_ok=True)

    args = [binary, "-p", "--output-format", "stream-json", "--verbose", "--model", model,
            "--system-prompt", SYSTEM_PROMPT, "--no-session-persistence",
            "--setting-sources=", "--strict-mcp-config", "--disable-slash-commands",
            "--tools", tools]
    if tools:
        args += ["--allowedTools", tools]

    try:
        proc = subprocess.run(
            args, input=prompt, capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=WORKDIR, timeout=timeout, shell=binary.endswith(".cmd"),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise ClaudeError("Claude hat zu lange gebraucht (Timeout).")

    result, rate_limit = None, None
    for line in proc.stdout.splitlines():
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("type") == "rate_limit_event":
            rate_limit = msg.get("rate_limit_info")
        elif msg.get("type") == "result":
            result = msg
    if not result:
        raise ClaudeError("Unerwartete Antwort der Claude CLI: " + (proc.stderr or proc.stdout)[:500])

    usage = _record_usage(kind, model, result, rate_limit)
    if result.get("is_error"):
        text = str(result.get("result") or "Fehler")
        if "login" in text.lower():
            raise ClaudeError('Claude CLI ist nicht eingeloggt. Im Terminal "claude" starten und /login ausfuehren.')
        raise ClaudeError(text)
    return str(result.get("result") or ""), usage


def _record_usage(kind: str, model: str, result: dict, rate_limit: dict | None) -> dict:
    u = result.get("usage") or {}
    entry = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        "model": next(iter(result.get("modelUsage") or {}), model),
        "input": u.get("input_tokens", 0),
        "cacheWrite": u.get("cache_creation_input_tokens", 0),
        "cacheRead": u.get("cache_read_input_tokens", 0),
        "output": u.get("output_tokens", 0),
        "webSearches": (u.get("server_tool_use") or {}).get("web_search_requests", 0),
        "costUsd": result.get("total_cost_usd", 0),
        "durationMs": result.get("duration_ms", 0),
        "rateLimit": rate_limit,
    }
    models.log_claude_usage(entry)
    entry["total"] = entry["input"] + entry["cacheWrite"] + entry["cacheRead"] + entry["output"]
    current = models.get_claude_usage(limit=1)
    return {"request": entry, "rateLimit": current["rateLimit"], "updatedAt": current["updatedAt"]}


def extract_json(text: str) -> dict:
    cleaned = re.sub(r"```(?:json)?", "", text)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ClaudeError("Claude hat kein JSON geliefert: " + text[:300])
    return json.loads(cleaned[start:end + 1])


def describe_date(iso: str) -> str:
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{WEEKDAYS[d.weekday()]}, {d.strftime('%d.%m.%Y')}"


# ── Prompts ──────────────────────────────────────────────────────

QUESTION_LEVELS = {
    "wenig": "Frage nur, wenn sonst ein grober Fehler (> 30 % bei kcal oder Preis) wahrscheinlich ist. Sonst schätzen.",
    "normal": "Frage bei jeder offenen Angabe, die kcal oder Preis um etwa 15 % oder mehr verändern kann.",
    "viel": "Frage bei jeder offenen Angabe, die das Ergebnis messbar verändert. Lieber eine Frage zu viel als eine Annahme.",
}
GOAL_TEXT = {
    "lose": "Fett verlieren", "recomp": "Recomp (Fett ab, Muskeln auf)", "maintain": "Gewicht halten",
    "muscle": "Muskelaufbau (Lean Bulk)", "gain": "zunehmen",
}


def lookup_prompt(text: str, date: str, meal: str | None, answers: list[dict],
                  research: str, menu: dict | None) -> str:
    profile = models.get_profile()
    favorites = models.list_favorites()
    fav_list = "\n".join(
        f"- {f['food_name']} ({f.get('amount_text') or '1 Portion'}): {f.get('calories')} kcal, "
        f"{f.get('protein_g')} g Eiweiß, Preis {f.get('price_eur') if f.get('price_eur') is not None else '?'} €"
        for f in favorites
    ) or "(keine)"

    menu_block = ""
    if menu:
        menu_block = f"""
OFFIZIELLER SPEISEPLAN {menu['name']}, {describe_date(date)}, von der App direkt geladen und exakt
(Preise für {profile['priceGroup']}, Nährwerte pro ausgegebener Portion; Quelle: {menu['url']}):
{menu['menu']}

Wenn der Nutzer in dieser Mensa gegessen hat, nimm Werte und Preise GENAU aus diesem Speiseplan.
Hier ist keine Websuche nötig. Ballaststoffe fehlen im Speiseplan, die schätzt du. Erfinde keine Gerichte, die nicht
in der Liste stehen. Passt kein Gericht eindeutig, frag nach und biete die passenden aus der Liste als Optionen an.
"""

    answers_block = ""
    if answers:
        answer_lines = "\n".join(
            f"- Frage: {a.get('question')}\n  Antwort: {a.get('answer') or '(keine Angabe, bitte sinnvoll schätzen)'}"
            for a in answers
        )
        research_block = (f"\nDeine bisherigen Rechercheergebnisse (verwende diese Werte, nicht neu schätzen):\n{research}\n"
                          if research else "")
        answers_block = f"""
Du hast bereits Rückfragen gestellt.{research_block}
Antworten des Nutzers:
{answer_lines}
Stelle jetzt nur noch dann eine weitere Rückfrage, wenn ohne sie ein grober Fehler (> 30 % kcal oder Preis) sicher wäre.
"""

    return f"""Du bist der Nährwert-Assistent einer lokalen Ernährungs- und Trainings-App.
Datum der Mahlzeit: {describe_date(date)} ({date}). Mahlzeit: {meal or 'unbekannt'}.
Preisgruppe des Nutzers (z.B. für Mensen): {profile['priceGroup']}.
Ernährungsweise/Hinweise: {profile.get('diet') or 'keine'}.

Der Nutzer beschreibt, was er gegessen hat. Ermittle für jedes einzelne Gericht/Lebensmittel die Nährwerte
für die tatsächlich gegessene Menge und den bezahlten Preis.
{menu_block}
Vorgehen:
1. Wird ein konkreter Ort/Produkt genannt (Restaurant, Marke, Supermarktprodukt oder eine Mensa ohne Speiseplan oben),
   suche mit WebSearch/WebFetch die offiziellen Angaben. Erfinde keine Gerichte oder Werte. Was du nicht findest,
   schätzt du und markierst es als Schätzung.
2. Passt ein Favorit des Nutzers, übernimm dessen Werte (skaliert auf die Menge).
3. Sonst schätze realistisch anhand üblicher Portionsgrößen und Nährwertdatenbanken.
4. Fehlende Einzelwerte (z.B. Ballaststoffe) schätze und vermerke das in "notes".
5. Preis: genannten Preis verwenden; bei offiziellen Angaben diesen; wenn klar gekauft aber unbekannt, schätzen
   und in "notes" vermerken; bei Selbstgekochtem/unklar Kosten grob schätzen oder null.

Favoriten des Nutzers:
{fav_list}

Beschreibung des Nutzers:
\"\"\"{text}\"\"\"
{answers_block}
Rückfragen: Wenn eine Angabe die Nährwerte ODER den Preis spürbar verändert und der Nutzer sie nicht genannt hat,
frage nach statt eine Annahme zu treffen. Maximal 3 kurze Fragen in einer Runde, jeweils mit 2–5 konkreten Antwortoptionen.
{QUESTION_LEVELS.get(profile.get('questionLevel'), '')}
Typische Fälle, in denen du fragen sollst:
- Supermarkt/Discounter-Produkte ohne Markenangabe (z.B. "Cola von Lidl"): Eigenmarke (bei Lidl z.B. Freeway) oder
  Markenprodukt (z.B. Coca-Cola)? Und welche Variante (normal / zero / light)? Nimm NICHT stillschweigend die Eigenmarke.
- Gebinde, wenn es den Preis bestimmt (z.B. 1 L Cola als 2 × 0,5 L, aus einer 1,25-L- oder 1,5-L-Flasche, Dose, Pfand?).
  Der Preis ist dann der Anteil an der gekauften Packung (z.B. 1 L aus einer 1,5-L-Flasche = 2/3 des Flaschenpreises).
  Gib dazu Optionen mit Preisen an, wenn du sie kennst.
- Mehrere passende Gerichte/Varianten (vegan vs. vegetarisch, klein vs. groß), unklare Portionsgröße, mehrdeutiger Ort.
Nicht fragen bei: Details, die das Ergebnis kaum ändern; Angaben, die schon in der Beschreibung oder in den Antworten stehen;
Favoriten, die eindeutig passen.

Antworte AUSSCHLIESSLICH mit einem JSON-Objekt (kein Markdown, kein Text davor oder danach) in einem dieser Formate:

A) Ergebnis:
{{"status":"ok","items":[{{"name":"Pizza Margherita (Pizzawerk, Mensa Adenauerring)","amount":"1 Pizza","kcal":1454,"protein":50,
"carbs":146,"sugar":11,"fat":73,"satfat":21,"fiber":8,"salt":5,"price":5.15,"source":"URL oder 'Schätzung'",
"confidence":"hoch|mittel|niedrig","notes":"kurzer Hinweis, z.B. Ballaststoffe geschätzt"}}],
"comment":"optionaler kurzer Hinweis an den Nutzer"}}

B) Rückfrage:
{{"status":"question","questions":[{{"question":"Vegetarische oder vegane Variante?","options":["vegetarisch","vegan"]}}],
"research":"PFLICHT: alle bisher gefundenen exakten Daten der infrage kommenden Optionen (Name, kcal, Eiweiß, KH, Zucker,
Fett, ges. Fett, Salz, Preis, Quelle), damit du nach der Antwort nicht erneut suchen musst",
"comment":"optional: kurzer Hinweis an den Nutzer"}}

Alle Mengen in Gramm (Salz in g), Energie in kcal, Preis in Euro als Zahl."""


def _profile_text(profile: dict) -> str:
    return (
        f"Profil: {'weiblich' if profile['sex'] == 'f' else 'männlich'}, {profile['age']} Jahre, "
        f"{profile['heightCm']} cm, {profile['weightKg']} kg, Körperfett "
        f"{str(profile['bodyFat']) + ' %' if profile.get('bodyFat') else 'unbekannt'}.\n"
        f"Training laut Profil: Kraft {profile.get('strengthDays') or 0}×/Woche, Ausdauer {profile.get('cardioDays') or 0}×/Woche.\n"
        f"Ziel: {GOAL_TEXT.get(profile['goal'], profile['goal'])}"
        f"{', Zielgewicht ' + str(profile['targetWeightKg']) + ' kg' if profile.get('targetWeightKg') else ''}.\n"
        f"Ernährungsweise: {profile.get('diet') or 'keine Angabe'}. Tagesbudget Essen: {profile.get('dailyBudget')} €."
    )


def _garmin_text(date: str) -> str:
    data = models.get_health(date)
    health, workouts = data.get("health") or {}, data.get("workouts") or []
    if not health and not workouts:
        return "Garmin: keine Daten für diesen Tag."
    lines = [f"Garmin heute: aktive kcal {health.get('active_calories') or '?'}, Schritte {health.get('steps') or '?'}, "
             f"Schlaf {health.get('sleep_hours') or '?'} h (Score {health.get('sleep_score') or '?'}), "
             f"HRV {health.get('hrv_avg') or '?'}, Body Battery {health.get('body_battery_low') or '?'}–{health.get('body_battery_high') or '?'}."]
    for w in workouts:
        lines.append(f"Workout: {w.get('activity_type')} {w.get('duration_min') or '?'} min, "
                     f"{w.get('calories_burned') or '?'} kcal, Load {w.get('training_load') or '?'}")
    return "\n".join(lines)


def advice_prompt(date: str, targets: dict, totals: dict) -> str:
    profile = models.get_profile()
    entries = models.get_food_log(date)["entries"]
    entry_lines = "\n".join(
        f"- [{e['meal_label']}] {e['food_name']} ({e.get('amount_text') or ''}): {e['calories']} kcal, "
        f"P {e['protein_g']} g, KH {e['carbs_g']} g, F {e['fat_g']} g, Ballaststoffe {e.get('fiber_g') or '?'} g, "
        f"{e.get('price_eur') if e.get('price_eur') is not None else '?'} €"
        for e in entries
    ) or "(noch nichts eingetragen)"
    return f"""Du bist ein freundlicher, knapper Ernährungscoach. Datum: {describe_date(date)}.
{_profile_text(profile)}
{_garmin_text(date)}

Tagesziele (aus Körperprofil + Garmin-Aktivität): {json.dumps({k: targets[k] for k in ('kcal', 'protein', 'carbs', 'fat', 'fiber', 'sugar', 'satfat', 'salt', 'budget')}, ensure_ascii=False)}
Herleitung Energie: {' + '.join(f"{s['label']} {s['kcal']}" for s in targets['steps'])} = {targets['kcal']} kcal
Bisher gegessen (Summe): {json.dumps(totals, ensure_ascii=False)}
Einträge:
{entry_lines}

Gib eine kurze Einschätzung (max. 120 Wörter, Deutsch, Markdown-Liste ok): Was fehlt heute noch, was ist schon zu viel,
und 2–3 konkrete, günstige Vorschläge für die restlichen Mahlzeiten passend zu Budget, Ernährungsweise und Training.
Bei Muskelaufbau/Recomp: achte besonders auf genug Eiweiß, verteilt über den Tag.
Keine Websuche nötig, außer der Nutzer isst offensichtlich in der Mensa; dann darfst du den heutigen Speiseplan prüfen."""


def report_prompt(context: str, nutrition_lines: str, today_targets: dict) -> str:
    profile = models.get_profile()
    return f"""Du bist ein erfahrener Athletik-, Erholungs- und Ernährungscoach.
{_profile_text(profile)}
Heutiges Tagesziel (aus Körperprofil + Garmin-Aktivität): {today_targets['kcal']} kcal, Eiweiß {today_targets['protein']} g,
Herleitung: {' + '.join(f"{s['label']} {s['kcal']}" for s in today_targets['steps'])}.

{context}

--- ERNÄHRUNG DER LETZTEN 7 TAGE (gegessen/Ziel) ---
{nutrition_lines or '(keine Einträge)'}

Analysiere Training, Erholung und Ernährung zusammen und gib einen kurzen, praxisnahen Coaching-Report auf Deutsch.
Berücksichtige HRV-Trends, Schlaf, Stress, Trainingsbelastung und ob Energie- und Eiweißzufuhr zum Training und Ziel passen.
Gib konkrete Empfehlungen für Training, Erholung, Schlaf und Ernährung. Maximal 400 Wörter, Markdown-Überschriften und Aufzählungen."""
