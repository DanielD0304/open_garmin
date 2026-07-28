"""
AI-Client fuer den Coaching-Report.

Nutzt eine OpenAI-kompatible Chat-Completions-API (kein lokales Modell mehr).
Default ist der kostenlose Groq-Tier; per .env laesst sich jeder andere
OpenAI-kompatible Anbieter einsetzen (OpenRouter, Together, Gemini-Compat, ...).

Relevante Environment-Variablen:
    AI_API_KEY    API-Key des Anbieters (Pflicht)
    AI_BASE_URL   Basis-URL, default https://api.groq.com/openai/v1
    AI_MODEL      Modellname, default llama-3.3-70b-versatile
    AI_TIMEOUT    Timeout in Sekunden, default 60
"""

from __future__ import annotations

import json
import os
import sys
from urllib import error as urllib_error, request as urllib_request

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_TIMEOUT = 60

SYSTEM_PROMPT = (
    "Du bist ein erfahrener Athletik- und Erholungs-Coach. "
    "Analysiere die folgenden Trainings- und Gesundheitsdaten und gib "
    "einen kurzen, praxisnahen Coaching-Report auf Deutsch. "
    "Beruecksichtige HRV-Trends, Schlafqualitaet, Stresslevel und Trainingsbelastung. "
    "Gib konkrete Empfehlungen fuer Training, Erholung und Schlaf. "
    "Halte den Report unter 500 Woertern. Formatiere mit Markdown-Ueberschriften und Aufzaehlungen."
)


def get_model() -> str:
    """Aktuell konfiguriertes Modell (fuer die Anzeige im Frontend)."""
    return os.environ.get("AI_MODEL", DEFAULT_MODEL)


def generate_ai_report(context: str) -> tuple[str | None, str | None]:
    """Ruft die Cloud-API auf und gibt (report, error) zurueck."""
    api_key = os.environ.get("AI_API_KEY", "").strip()
    if not api_key:
        return None, "AI_API_KEY fehlt. Trage den API-Key in die .env ein (siehe .env.example)."

    base_url = os.environ.get("AI_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    model = get_model()
    try:
        timeout = int(os.environ.get("AI_TIMEOUT", DEFAULT_TIMEOUT))
    except ValueError:
        timeout = DEFAULT_TIMEOUT

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        "temperature": 0.7,
        "max_tokens": 900,
        "stream": False,
    }

    print(f"[AI] Sende Anfrage an {base_url} (Modell: {model})...", flush=True)

    request = urllib_request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib_request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
        print("[AI] Antwort erfolgreich erhalten!", flush=True)
    except urllib_error.HTTPError as e:
        body = e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""
        err_msg = _http_error_message(e.code, body)
        print(f"[AI Error] {err_msg}", file=sys.stderr, flush=True)
        return None, err_msg
    except (urllib_error.URLError, TimeoutError, ValueError) as e:
        err_msg = f"Connection/Timeout Error: {e}"
        print(f"[AI Error] {err_msg}", file=sys.stderr, flush=True)
        return None, err_msg

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        err_msg = f"JSON Decode Error: {e}"
        print(f"[AI Error] {err_msg}", file=sys.stderr, flush=True)
        return None, err_msg

    choices = parsed.get("choices") or []
    report = (choices[0].get("message", {}).get("content") if choices else None)
    if not isinstance(report, str) or not report.strip():
        return None, "Die API hat keinen oder einen leeren Report generiert."
    return report.strip(), None


def _http_error_message(code: int, body: str) -> str:
    """Macht die haeufigen API-Fehler lesbar."""
    detail = body.strip()
    try:
        parsed = json.loads(body)
        detail = (parsed.get("error") or {}).get("message") or detail
    except (json.JSONDecodeError, AttributeError):
        pass

    if code == 401:
        return f"HTTP 401: API-Key ungueltig oder abgelaufen. {detail}"
    if code == 404:
        return f"HTTP 404: Modell '{get_model()}' existiert bei diesem Anbieter nicht. {detail}"
    if code == 429:
        return f"HTTP 429: Free-Tier-Limit erreicht, spaeter erneut versuchen. {detail}"
    return f"HTTP Error {code}: {detail[:500]}"
