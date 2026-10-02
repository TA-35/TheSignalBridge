"""POST /api/review - the proxy to the inference service.

The service is never started here. Everything is faked at the urllib seam,
so these tests run in CI with no model, no key and no network - the same
constraint the existing backend tests already satisfy.
"""
import json
import urllib.error
from unittest.mock import patch

import pytest

from app import create_app


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


GOOD = {"stage": "review", "degraded": False, "summary": "A Friday deadline.",
        "claims": [{"field": "deadline", "text": "Friday", "span": [43, 49]}],
        "unstated": [], "missing": []}


# --------------------------------------------------------------------------
# The existing API must be untouched
# --------------------------------------------------------------------------

def test_decode_is_unaffected_by_the_new_route(client):
    r = client.post("/api/decode", json={"message": "Send the deck by Friday."})
    assert r.status_code == 200
    assert set(r.get_json()) >= {"elements", "covered", "missing", "category"}


def test_patterns_is_unaffected(client):
    assert client.get("/api/patterns").status_code in (200, 500)  # 500 = no DB in CI


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------

def test_review_forwards_and_returns_the_service_response(client):
    with patch("urllib.request.urlopen", return_value=_Response(GOOD)):
        r = client.post("/api/review", json={"message": "Send it by Friday."})
    assert r.status_code == 200
    assert r.get_json()["summary"] == "A Friday deadline."


def test_quick_stage_hits_the_analyse_endpoint(client):
    seen = {}

    def fake(req, timeout=None):
        seen["url"] = req.full_url
        return _Response({"stage": "analyse", "message_type": "request"})

    with patch("urllib.request.urlopen", side_effect=fake):
        r = client.post("/api/review/quick", json={"message": "Send it Friday."})
    assert r.status_code == 200
    assert seen["url"].endswith("/analyse")


def test_full_stage_hits_the_review_endpoint(client):
    seen = {}

    def fake(req, timeout=None):
        seen["url"] = req.full_url
        return _Response(GOOD)

    with patch("urllib.request.urlopen", side_effect=fake):
        client.post("/api/review", json={"message": "Send it Friday."})
    assert seen["url"].endswith("/review")


# --------------------------------------------------------------------------
# Every failure mode degrades rather than erroring
# --------------------------------------------------------------------------

@pytest.mark.parametrize("failure,expected", [
    (urllib.error.URLError(ConnectionRefusedError()), "unreachable"),
    (urllib.error.HTTPError("u", 500, "boom", {}, None), "error 500"),
    (TimeoutError(), "timed out"),
    (RuntimeError("anything"), "failed"),
])
def test_a_broken_inference_service_degrades_with_200(client, failure, expected):
    """The reader pasted a message. They get a reduced answer, not an error
    page - and the frontend has one shape to render either way."""
    with patch("urllib.request.urlopen", side_effect=failure):
        r = client.post("/api/review", json={"message": "Send it by Friday."})
    assert r.status_code == 200
    body = r.get_json()
    assert body["degraded"] is True
    assert expected in " ".join(body["degraded_reason"])
    for key in ("summary", "claims", "missing", "unstated"):
        assert key in body


def test_an_unconfigured_deploy_says_so_plainly(client):
    client.application.config["INFERENCE_URL"] = ""
    r = client.post("/api/review", json={"message": "Send it by Friday."})
    assert r.status_code == 200
    assert "INFERENCE_URL unset" in " ".join(r.get_json()["degraded_reason"])


# --------------------------------------------------------------------------
# Input guards, matching /api/decode
# --------------------------------------------------------------------------

@pytest.mark.parametrize("payload", [{}, {"message": ""}, {"message": "   "},
                                     {"message": 42}])
def test_an_empty_message_is_a_400(client, payload):
    assert client.post("/api/review", json=payload).status_code == 400


def test_an_over_long_message_is_a_413(client):
    r = client.post("/api/review", json={"message": "x" * 5001})
    assert r.status_code == 413


def test_the_limit_matches_the_decode_route(client):
    from app.routes import decode, review
    assert review.MAX_MESSAGE_LENGTH == decode.MAX_MESSAGE_LENGTH


def test_a_4xx_from_the_service_keeps_its_meaning(client):
    err = urllib.error.HTTPError(
        "u", 413, "too long", {},
        __import__("io").BytesIO(json.dumps({"error": "Message is too long."}).encode()))
    with patch("urllib.request.urlopen", side_effect=err):
        r = client.post("/api/review", json={"message": "Send it Friday."})
    assert r.status_code == 413


# --------------------------------------------------------------------------
# Health
# --------------------------------------------------------------------------

def test_health_reports_unreachable_without_erroring(client):
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("x")):
        r = client.get("/api/review/health")
    assert r.status_code == 200
    assert r.get_json()["reachable"] is False


def test_health_reports_reachable(client):
    with patch("urllib.request.urlopen",
               return_value=_Response({"status": "ok", "model": "m"})):
        r = client.get("/api/review/health")
    assert r.get_json()["reachable"] is True
