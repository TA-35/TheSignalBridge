"""Per-IP rate limiting on the unauthenticated API.

Why this exists: api.thesignalbridge.com has no auth, and every POST to
/api/review makes an LLM call that costs money. Before this, five
unauthenticated calls in a row all returned 200.

The limiter is disabled under TESTING so it cannot make unrelated tests fail
in an order-dependent way, so every test here turns it back on explicitly and
resets the store first - otherwise the second test in the file inherits the
first one's exhausted budget.
"""
import json
from unittest.mock import patch

import pytest

from app import create_app
from app.limiter import limiter


@pytest.fixture
def client(monkeypatch):
    # Enabled through the environment BEFORE create_app, not on the app after
    # it. flask-limiter only builds its storage when limiting is on at init,
    # so flipping the flag afterwards leaves `limiter.reset()` asserting on a
    # storage that was never created. Setting it here also means these tests
    # exercise the same path production takes.
    monkeypatch.setenv("SECRET_KEY", "test-only")
    monkeypatch.setenv("RATELIMIT_ENABLED", "true")
    app = create_app()
    app.config["INFERENCE_URL"] = ""      # /review degrades without a service
    limiter.reset()
    yield app.test_client()
    limiter.reset()


def _review(client, ip="203.0.113.10", forwarded=None):
    """One /api/review call, arriving as nginx would deliver it.

    nginx builds X-Forwarded-For with $proxy_add_x_forwarded_for, which
    APPENDS the real peer address to whatever the client sent. `forwarded`
    is what the client claimed; `ip` is the address nginx actually saw.
    """
    chain = f"{forwarded}, {ip}" if forwarded else ip
    return client.post(
        "/api/review",
        json={"message": "Could you send the report by Friday?"},
        headers={"X-Forwarded-For": chain},
    )


def test_the_expensive_endpoint_stops_answering_once_the_limit_is_hit(client):
    """5 per minute on /api/review - the sixth call must not reach the model."""
    codes = [_review(client).status_code for _ in range(6)]
    assert codes[:5] == [200] * 5, codes
    assert codes[5] == 429, f"sixth call was {codes[5]}, expected 429"


def test_the_429_body_is_json_like_every_other_error(client):
    """Werkzeug's default 429 is HTML. The frontend reads `error`."""
    for _ in range(5):
        _review(client)
    response = _review(client)
    assert response.status_code == 429
    assert response.is_json, response.get_data(as_text=True)[:80]
    assert "error" in response.get_json()


def test_two_addresses_get_separate_budgets(client):
    """The point of ProxyFix. Without it every request keys on 127.0.0.1 and
    one busy client throttles everybody - an outage caused by the defence."""
    for _ in range(5):
        assert _review(client, ip="203.0.113.10").status_code == 200
    assert _review(client, ip="203.0.113.10").status_code == 429
    assert _review(client, ip="198.51.100.77").status_code == 200, (
        "a second address was throttled by the first one's usage - "
        "the limiter is keying on something shared, probably the loopback"
    )


def test_a_forged_forwarded_header_does_not_buy_a_new_identity(client):
    """The attack this ordering defends against.

    A caller who can pick their own key has no limit at all - they just send
    a new one each request. nginx appends the real peer address, so the
    rightmost entry is the only trustworthy one, and ProxyFix(x_for=1) reads
    exactly that. Reading the LEFTMOST entry - which is what "just use
    X-Forwarded-For" usually means - would make every one of these calls look
    like a different client and none of them would ever be throttled.
    """
    for i in range(5):
        assert _review(client, ip="203.0.113.10",
                       forwarded=f"10.0.0.{i}").status_code == 200
    blocked = _review(client, ip="203.0.113.10", forwarded="10.0.0.99")
    assert blocked.status_code == 429, (
        "a fresh forged X-Forwarded-For got a fresh budget - the limiter is "
        "trusting the client-supplied end of the chain"
    )


def test_the_health_check_is_never_throttled(client):
    """It is what a deploy and a monitor use to ask whether the service is up.
    Throttling it means the thing you reach for when the site looks broken is
    the first thing to stop answering."""
    for _ in range(40):
        assert client.get("/api/review/health").status_code == 200


def test_the_cheap_endpoint_is_looser_than_the_expensive_one(client):
    """/api/decode runs spaCy locally in ~6ms and costs nothing, so it must
    not inherit the model endpoint's budget."""
    for _ in range(6):
        response = client.post("/api/decode",
                               json={"message": "send the report by friday"},
                               headers={"X-Forwarded-For": "203.0.113.55"})
        assert response.status_code != 429, "decode hit the model endpoint's limit"


def test_the_suite_runs_with_limits_off(monkeypatch):
    """Every other test file makes many calls from one address in seconds, so
    conftest disables limiting for the suite. This pins that: without it, the
    failure is an unrelated test 429ing depending on execution order, which is
    a genuinely confusing thing to debug.

    Pinning the mechanism too, not just the value - an earlier version derived
    this from TESTING, which is set on the app AFTER create_app has already
    attached the limiter, so it read False and left limiting on everywhere."""
    monkeypatch.setenv("SECRET_KEY", "test-only")
    app = create_app()
    assert app.config["RATELIMIT_ENABLED"] is False


def test_the_switch_is_honoured_when_limiting_is_disabled(monkeypatch):
    """Disabled must mean disabled - the rollback if these limits ever turn
    out to be too tight in front of real users."""
    monkeypatch.setenv("SECRET_KEY", "test-only")
    monkeypatch.setenv("RATELIMIT_ENABLED", "false")
    app = create_app()
    app.config["INFERENCE_URL"] = ""
    client = app.test_client()
    # Well past "5 per minute" - none of these may be refused.
    for _ in range(8):
        assert _review(client, ip="203.0.113.201").status_code == 200
