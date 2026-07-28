"""AI-Client: Fehlerpfade und Antwort-Parsing ohne echten API-Call."""

import io
import json
from urllib import error as urllib_error

from db import ai_client


class FakeResponse:
    """Minimaler Ersatz fuer das urlopen-Kontextobjekt."""

    def __init__(self, body: str):
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def patch_urlopen(monkeypatch, handler):
    monkeypatch.setattr(ai_client.urllib_request, "urlopen", handler)


def chat_response(content: str) -> str:
    return json.dumps({"choices": [{"message": {"role": "assistant", "content": content}}]})


def http_error(code: int, body: dict) -> urllib_error.HTTPError:
    return urllib_error.HTTPError(
        url="https://example.test/chat/completions",
        code=code,
        msg="error",
        hdrs=None,
        fp=io.BytesIO(json.dumps(body).encode("utf-8")),
    )


# ── Konfiguration ────────────────────────────────────────────────

def test_missing_key_reports_clear_error(no_ai_key):
    report, error = ai_client.generate_ai_report("daten")

    assert report is None
    assert "AI_API_KEY" in error


def test_model_comes_from_env(monkeypatch):
    monkeypatch.setenv("AI_MODEL", "mein-modell")
    assert ai_client.get_model() == "mein-modell"


def test_default_model_when_unset(monkeypatch):
    monkeypatch.delenv("AI_MODEL", raising=False)
    assert ai_client.get_model() == ai_client.DEFAULT_MODEL


# ── Erfolgsfall ──────────────────────────────────────────────────

def test_successful_report(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-key")
    patch_urlopen(monkeypatch, lambda req, timeout=None: FakeResponse(chat_response("# Report\n- alles gut")))

    report, error = ai_client.generate_ai_report("daten")

    assert error is None
    assert report.startswith("# Report")


def test_request_carries_auth_and_model(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "geheim")
    monkeypatch.setenv("AI_MODEL", "test-modell")
    monkeypatch.setenv("AI_BASE_URL", "https://example.test/v1")
    captured = {}

    def handler(req, timeout=None):
        captured["url"] = req.full_url
        captured["auth"] = req.get_header("Authorization")
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse(chat_response("ok"))

    patch_urlopen(monkeypatch, handler)
    ai_client.generate_ai_report("meine daten")

    assert captured["url"] == "https://example.test/v1/chat/completions"
    assert captured["auth"] == "Bearer geheim"
    assert captured["body"]["model"] == "test-modell"
    assert captured["body"]["messages"][-1]["content"] == "meine daten"


def test_trailing_slash_in_base_url_is_handled(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("AI_BASE_URL", "https://example.test/v1/")
    captured = {}

    def handler(req, timeout=None):
        captured["url"] = req.full_url
        return FakeResponse(chat_response("ok"))

    patch_urlopen(monkeypatch, handler)
    ai_client.generate_ai_report("daten")

    assert captured["url"] == "https://example.test/v1/chat/completions"


# ── Fehlerpfade ──────────────────────────────────────────────────

def test_rate_limit_message_is_actionable(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-key")

    def handler(req, timeout=None):
        raise http_error(429, {"error": {"message": "Rate limit reached"}})

    patch_urlopen(monkeypatch, handler)
    report, error = ai_client.generate_ai_report("daten")

    assert report is None
    assert "429" in error and "Limit" in error


def test_invalid_key_message(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "falsch")

    def handler(req, timeout=None):
        raise http_error(401, {"error": {"message": "Invalid API Key"}})

    patch_urlopen(monkeypatch, handler)
    report, error = ai_client.generate_ai_report("daten")

    assert report is None
    assert "401" in error and "ungueltig" in error


def test_unknown_model_message_names_the_model(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "k")
    monkeypatch.setenv("AI_MODEL", "gibts-nicht")

    def handler(req, timeout=None):
        raise http_error(404, {"error": {"message": "model not found"}})

    patch_urlopen(monkeypatch, handler)
    report, error = ai_client.generate_ai_report("daten")

    assert "gibts-nicht" in error


def test_connection_error_is_caught(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "k")

    def handler(req, timeout=None):
        raise urllib_error.URLError("kein netz")

    patch_urlopen(monkeypatch, handler)
    report, error = ai_client.generate_ai_report("daten")

    assert report is None
    assert "Connection" in error


def test_malformed_json_is_caught(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "k")
    patch_urlopen(monkeypatch, lambda req, timeout=None: FakeResponse("kein json"))

    report, error = ai_client.generate_ai_report("daten")

    assert report is None
    assert "JSON" in error


def test_empty_content_is_treated_as_failure(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "k")
    patch_urlopen(monkeypatch, lambda req, timeout=None: FakeResponse(chat_response("   ")))

    report, error = ai_client.generate_ai_report("daten")

    assert report is None
    assert "leeren" in error


def test_missing_choices_is_treated_as_failure(monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "k")
    patch_urlopen(monkeypatch, lambda req, timeout=None: FakeResponse(json.dumps({"choices": []})))

    report, error = ai_client.generate_ai_report("daten")

    assert report is None
    assert error is not None
