"""POST /api/compose - the proxy to the inference service's Compose endpoints.

As in test_review_route.py, the service is never started: everything is faked
at the urllib seam, so these run in CI with no model, no key and no network.
"""
import json
import urllib.error
from unittest.mock import patch

import pytest

from app import create_app
from app.routes import compose, review


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-only")
    app = create_app()
    app.config["INFERENCE_URL"] = "http://127.0.0.1:9999"
    return app.test_client()


class _Response:
    """Minimal stand-in for what urlopen returns."""

    def __init__(self, payload, status=200):
        self._body = json.dumps(payload).encode()
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


MEANING = {"ask": "Check the deck", "deadline": "Friday", "urgency": "medium", "tone": "casual", "implied": ""}
GOOD = {"stage": "compose", "degraded": False, "degraded_reason": [],
        "rewrite": "Could you check the deck before Friday?", "notes": ["Made the ask direct."],
        "meaning": MEANING, "checks": {"entities_kept": True, "nothing_added": True, "no_contradiction": True},
        "model": "qwen3.5-4b-ft"}
DEGRADED_KEYS = {"stage", "degraded", "degraded_reason", "rewrite", "notes", "meaning"}


def test_review_is_unaffected_by_the_new_route(client):
    with patch("urllib.request.urlopen", return_value=_Response({"stage": "review", "summary": "x"})):
        assert client.post("/api/review", json={"message": "Send it."}).get_json()["summary"] == "x"


def test_compose_forwards_to_the_compose_endpoint(client):
    seen = {}

    def fake(req, timeout=None):
        seen.update(url=req.full_url, body=json.loads(req.data), timeout=timeout)
        return _Response(GOOD)

    with patch("urllib.request.urlopen", side_effect=fake):
        r = client.post("/api/compose", json={"message": "can u check the deck before friday"})
    assert r.status_code == 200 and r.get_json() == GOOD
    assert seen["url"].endswith("/compose") and seen["body"] == {"message": "can u check the deck before friday"}
    assert seen["timeout"] == 100.0


def test_quick_forwards_to_the_quick_endpoint(client):
    seen = {}
    signals = {"stage": "analyse", "signals": [{"model": "tone", "label": "casual", "confidence": 0.9}]}

    def fake(req, timeout=None):
        seen["url"] = req.full_url
        return _Response(signals)

    with patch("urllib.request.urlopen", side_effect=fake):
        r = client.post("/api/compose/quick", json={"message": "can u check the deck"})
    assert r.get_json() == signals and seen["url"].endswith("/compose/quick")


@pytest.mark.parametrize("failure,expected", [
    (urllib.error.URLError(ConnectionRefusedError()), "unreachable"),
    (urllib.error.HTTPError("u", 500, "boom", {}, None), "error 500"),
    (TimeoutError(), "timed out"),
    (RuntimeError("anything"), "failed"),
])
def test_a_broken_service_degrades_with_200_and_no_rewrite(client, failure, expected):
    with patch("urllib.request.urlopen", side_effect=failure):
        r = client.post("/api/compose", json={"message": "can u check the deck"})
    body = r.get_json()
    assert r.status_code == 200 and set(body) == DEGRADED_KEYS
    assert body["degraded"] is True and body["rewrite"] is None
    assert expected in " ".join(body["degraded_reason"])


def test_a_degraded_answer_never_carries_a_rewrite(client):
    leaky = dict(GOOD, degraded=True, degraded_reason=["dropped_entity"])
    with patch("urllib.request.urlopen", return_value=_Response(leaky)):
        body = client.post("/api/compose", json={"message": "can u check the deck"}).get_json()
    assert body["rewrite"] is None and body["degraded_reason"] == ["dropped_entity"]


def test_a_broken_quick_stage_answers_empty_signals(client):
    with patch("urllib.request.urlopen", side_effect=TimeoutError()):
        r = client.post("/api/compose/quick", json={"message": "can u check the deck"})
    assert r.status_code == 200 and r.get_json() == {"stage": "analyse", "signals": []}


def test_an_unconfigured_deploy_says_so_plainly(client):
    client.application.config["INFERENCE_URL"] = ""
    body = client.post("/api/compose", json={"message": "can u check the deck"}).get_json()
    assert "INFERENCE_URL unset" in " ".join(body["degraded_reason"]) and body["rewrite"] is None


@pytest.mark.parametrize("path", ["/api/compose", "/api/compose/quick"])
@pytest.mark.parametrize("payload", [{}, {"message": ""}, {"message": "   "}, {"message": 42}])
def test_an_empty_message_is_a_400(client, path, payload):
    assert client.post(path, json=payload).status_code == 400


@pytest.mark.parametrize("path", ["/api/compose", "/api/compose/quick"])
def test_an_over_long_message_is_a_413(client, path):
    r = client.post(path, json={"message": "a" * (compose.MAX_MESSAGE_LENGTH + 1)})
    assert r.status_code == 413 and "2000" in r.get_json()["error"]


def test_compose_has_its_own_lower_limit():
    assert compose.MAX_MESSAGE_LENGTH == 2000 < review.MAX_MESSAGE_LENGTH


def test_a_4xx_from_the_service_keeps_its_meaning(client):
    err = urllib.error.HTTPError("u", 413, "too long", {}, None)
    err.read = lambda: json.dumps({"error": "Message is too long."}).encode()
    with patch("urllib.request.urlopen", side_effect=err):
        r = client.post("/api/compose", json={"message": "can u check the deck"})
    assert r.status_code == 413 and r.get_json() == {"error": "Message is too long."}
