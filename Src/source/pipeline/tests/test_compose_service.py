"""Compose service tests. The model, the classifiers and the grounding check
are faked, so these run in CI with no model, no torch and no network."""
from __future__ import annotations

import json

import pytest

from Src.source.pipeline import compose_client, compose_prompt as cp, compose_service as cs, grounding

SIGNALS = [{"model": "tone", "label": "casual", "confidence": 0.9},
           {"model": "politeness", "label": "high", "confidence": 0.555},
           {"model": "circa", "label": "direct", "confidence": 0.6}]
MEANING = {"ask": "Check the deck", "deadline": "Friday", "urgency": "medium", "tone": "casual", "implied": ""}
PASS = grounding.Grounding(True, True, True)
DROPPED = grounding.Grounding(False, True, None, (grounding.DROPPED,))
MESSAGE = "no rush but could you maybe check the deck before Friday?"


def _answer(rewrite):
    return {"meaning": MEANING, "rewrite": rewrite, "notes": ["Made the ask direct."], "raw": "{}", "seconds": 1.0}


@pytest.fixture
def fake(monkeypatch):
    """Compose switched on, with scripted model answers and grounding verdicts."""
    monkeypatch.setenv("COMPOSE_LLM_URL", "http://127.0.0.1:8080")
    monkeypatch.delenv("COMPOSE_FEW_SHOT", raising=False)
    monkeypatch.delenv("COMPOSE_MODEL_NAME", raising=False)
    monkeypatch.setattr(cs, "signals", lambda message: SIGNALS)
    script = {"answers": [], "verdicts": [], "calls": []}

    def complete(message, signals, **kw):
        script["calls"].append(kw)
        answer = script["answers"].pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(compose_client, "complete", complete)
    monkeypatch.setattr(grounding, "check", lambda source, rewrite: script["verdicts"].pop(0))
    return script


def test_a_grounded_rewrite_is_returned_with_its_checks(fake):
    fake["answers"] = [_answer("Could you check the deck before Friday?")]
    fake["verdicts"] = [PASS]
    out = cs.compose(MESSAGE)
    assert out["degraded"] is False and out["degraded_reason"] == []
    assert out["rewrite"] == "Could you check the deck before Friday?"
    assert out["meaning"] == MEANING and out["notes"] == ["Made the ask direct."]
    assert out["signals"] == SIGNALS and out["model"] == "qwen3.5-4b-ft"
    assert out["checks"] == {"entities_kept": True, "nothing_added": True, "no_contradiction": True}
    assert "raw" not in out and "seconds" not in out
    assert fake["calls"] == [{"few_shot": False, "base_url": "http://127.0.0.1:8080",
                              "temperature": 0.3, "timeout": 45.0}]


def test_a_failed_check_retries_once_at_a_lower_temperature(fake):
    fake["answers"] = [_answer("Could you check the deck?"), _answer("Could you check the deck before Friday?")]
    fake["verdicts"] = [DROPPED, PASS]
    out = cs.compose(MESSAGE)
    assert out["rewrite"] == "Could you check the deck before Friday?" and not out["degraded"]
    assert [c["temperature"] for c in fake["calls"]] == [0.3, 0.1]


def test_two_failed_checks_withhold_the_rewrite(fake):
    fake["answers"] = [_answer("Could you check it?"), _answer("Could you check it soon?")]
    fake["verdicts"] = [DROPPED, DROPPED]
    out = cs.compose(MESSAGE)
    assert out["degraded"] is True and out["rewrite"] is None
    assert out["degraded_reason"] == [grounding.DROPPED]
    assert out["notes"] == [] and out["meaning"] == cs.EMPTY_MEANING
    assert out["signals"] == SIGNALS


def test_already_clear_returns_the_message_itself_unchecked(fake):
    # The model said nothing needed changing but still "fixed" its copy. The
    # sender gets their own words back, which have nothing to verify.
    fake["answers"] = [dict(_answer("No rush, but could you maybe check the deck before Fri?"),
                            notes=[cp.ALREADY_CLEAR_NOTE])]
    out = cs.compose(MESSAGE)            # no verdicts scripted: a grounding call would fail
    assert out["degraded"] is False and out["rewrite"] == MESSAGE
    assert out["notes"] == [cp.ALREADY_CLEAR_NOTE] and out["meaning"] == MEANING
    assert out["checks"] == {"entities_kept": True, "nothing_added": True, "no_contradiction": True}


def test_an_unusable_reply_is_retried(fake):
    fake["answers"] = [cp.ComposeOutputError("no JSON object"), _answer("Could you check the deck before Friday?")]
    fake["verdicts"] = [PASS]
    assert cs.compose(MESSAGE)["degraded"] is False


def test_two_unusable_replies_degrade_as_invalid_output(fake):
    fake["answers"] = [cp.ComposeOutputError("no JSON object")] * 2
    assert cs.compose(MESSAGE)["degraded_reason"] == [cs.INVALID_OUTPUT]


def test_an_unreachable_model_is_not_retried(fake):
    fake["answers"] = [compose_client.ComposeServerError("cannot reach")]
    out = cs.compose(MESSAGE)
    assert out["degraded_reason"] == [cs.MODEL_UNAVAILABLE] and len(fake["calls"]) == 1


def test_compose_is_off_until_its_url_is_set(fake, monkeypatch):
    monkeypatch.delenv("COMPOSE_LLM_URL")
    out = cs.compose(MESSAGE)
    assert out["degraded_reason"] == [cs.NOT_CONFIGURED] and fake["calls"] == []
    assert out["signals"] == SIGNALS


def test_the_baseline_runs_few_shot_and_says_so(fake, monkeypatch):
    monkeypatch.setenv("COMPOSE_FEW_SHOT", "1")
    fake["answers"] = [_answer("Could you check the deck before Friday?")]
    fake["verdicts"] = [PASS]
    out = cs.compose(MESSAGE)
    assert fake["calls"][0]["few_shot"] is True and out["model"] == "qwen3.5-4b-baseline"


def test_degraded_reasons_never_carry_message_text(fake):
    fake["answers"] = [_answer("x"), _answer("y")]
    fake["verdicts"] = [grounding.Grounding(False, False, None, (grounding.DROPPED, grounding.ADDED))] * 2
    reasons = cs.compose(MESSAGE)["degraded_reason"]
    assert reasons == [grounding.DROPPED, grounding.ADDED]
    assert not any(word in " ".join(reasons) for word in ("deck", "Friday", "rush"))


def test_signals_come_back_in_the_contract_shape(monkeypatch):
    def adapter(name, label):
        return lambda *a, **k: {"model": name, "label": label, "confidence": 0.5, "note": "dropped"}

    monkeypatch.setattr(cs.tone, "predict", adapter("tone", "casual"))
    monkeypatch.setattr(cs.politeness, "predict", adapter("politeness", "high"))
    monkeypatch.setattr(cs.circa, "predict", adapter("circa", "direct"))
    assert cs.signals(MESSAGE) == [{"model": "tone", "label": "casual", "confidence": 0.5},
                                   {"model": "politeness", "label": "high", "confidence": 0.5},
                                   {"model": "circa", "label": "direct", "confidence": 0.5}]


# --------------------------------------------------------------------------
# The HTTP endpoints on the inference service
# --------------------------------------------------------------------------

@pytest.fixture
def client(monkeypatch):
    flask = pytest.importorskip("flask")  # noqa: F841 - the service's own dependency
    monkeypatch.delenv("PIPELINE_SERVICE_TOKEN", raising=False)
    from Src.source.pipeline.service import create_service
    return create_service(warm=False).test_client()


def test_compose_endpoint_returns_the_answer(client, fake):
    fake["answers"] = [_answer("Could you check the deck before Friday?")]
    fake["verdicts"] = [PASS]
    r = client.post("/compose", json={"message": MESSAGE})
    assert r.status_code == 200 and r.get_json()["rewrite"] == "Could you check the deck before Friday?"


def test_quick_endpoint_returns_signals_only(client, fake):
    r = client.post("/compose/quick", json={"message": MESSAGE})
    assert r.get_json() == {"stage": "analyse", "signals": SIGNALS} and fake["calls"] == []


@pytest.mark.parametrize("path", ["/compose", "/compose/quick"])
def test_empty_and_too_long_messages_are_refused(client, fake, path):
    assert client.post(path, json={"message": "  "}).status_code == 400
    assert client.post(path, json={"message": "a" * (cs.MAX_MESSAGE_CHARS + 1)}).status_code == 413


def test_an_unexpected_error_still_answers_degraded(client, fake, monkeypatch):
    def broken(message):
        raise RuntimeError("boom")

    monkeypatch.setattr(cs, "compose", broken)
    body = client.post("/compose", json={"message": MESSAGE}).get_json()
    assert body["degraded"] is True and body["rewrite"] is None
    assert body["degraded_reason"] == ["compose error: RuntimeError"]


def test_health_says_whether_compose_is_on(client, fake):
    compose = client.get("/health").get_json()["compose"]
    assert compose["enabled"] is True and compose["max_message_chars"] == cs.MAX_MESSAGE_CHARS


# --------------------------------------------------------------------------
# Remote mode: a small host hands Compose to another service (the uni GPU
# server through a tunnel) and loads nothing itself
# --------------------------------------------------------------------------

class _Reply:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@pytest.fixture
def remote(monkeypatch):
    """COMPOSE_REMOTE_URL set; records every request urllib makes."""
    monkeypatch.delenv("COMPOSE_LLM_URL", raising=False)
    monkeypatch.setenv("COMPOSE_REMOTE_URL", "http://127.0.0.1:18100")
    monkeypatch.delenv("COMPOSE_REMOTE_TOKEN", raising=False)
    sent, auth = [], []

    def answer(payload):
        def fake_urlopen(req, timeout=None):
            sent.append({"url": req.full_url, "body": json.loads(req.data), "timeout": timeout})
            auth.append(req.get_header("Authorization"))
            if isinstance(payload, Exception):
                raise payload
            return _Reply(payload)
        monkeypatch.setattr(cs.urllib.request, "urlopen", fake_urlopen)

    monkeypatch.setattr(compose_client, "complete", lambda *a, **k: pytest.fail("must not call a local model"))
    monkeypatch.setattr(grounding, "check", lambda *a, **k: pytest.fail("must not check locally"))
    answer.sent, answer.auth = sent, auth
    return answer


def test_remote_compose_returns_the_remote_answer(remote):
    answer = {"stage": "compose", "degraded": False, "degraded_reason": [], "rewrite": "Could you check it?",
              "notes": ["Made the ask direct."], "meaning": MEANING, "model": "qwen3.5-4b-ft"}
    remote(answer)
    assert cs.compose(MESSAGE) == answer
    assert remote.sent == [{"url": "http://127.0.0.1:18100/compose", "body": {"message": MESSAGE}, "timeout": 25.0}]


def test_remote_degraded_answer_never_carries_a_rewrite(remote):
    remote({"stage": "compose", "degraded": True, "degraded_reason": ["dropped_entity"],
            "rewrite": "leaked", "notes": [], "meaning": cs.EMPTY_MEANING})
    out = cs.compose(MESSAGE)
    assert out["rewrite"] is None and out["degraded_reason"] == ["dropped_entity"]


def test_unreachable_remote_degrades(remote):
    remote(OSError("tunnel down"))
    out = cs.compose(MESSAGE)
    assert out["degraded"] is True and out["degraded_reason"] == [cs.MODEL_UNAVAILABLE]
    assert out["rewrite"] is None


def test_remote_quick_stage(remote):
    remote({"stage": "analyse", "signals": SIGNALS})
    assert cs.signals(MESSAGE) == SIGNALS
    assert remote.sent[0]["url"] == "http://127.0.0.1:18100/compose/quick"
    remote(TimeoutError())
    assert cs.signals(MESSAGE) == []


def test_health_says_compose_is_remote(remote):
    pytest.importorskip("flask")
    from Src.source.pipeline.service import create_service
    compose = create_service(warm=False).test_client().get("/health").get_json()["compose"]
    assert compose["enabled"] is True and compose["remote"] is True


def test_remote_calls_carry_the_token_only_when_one_is_set(remote, monkeypatch):
    remote({"stage": "analyse", "signals": SIGNALS})
    cs.signals(MESSAGE)
    monkeypatch.setenv("COMPOSE_REMOTE_TOKEN", "s3cret")
    cs.signals(MESSAGE)
    remote({"stage": "compose", "degraded": True, "degraded_reason": ["dropped_entity"]})
    cs.compose(MESSAGE)
    assert remote.auth == [None, "Bearer s3cret", "Bearer s3cret"]


@pytest.fixture
def locked(monkeypatch, fake):
    """The service with PIPELINE_SERVICE_TOKEN set, as on the uni GPU server."""
    pytest.importorskip("flask")
    monkeypatch.setenv("PIPELINE_SERVICE_TOKEN", "s3cret")
    from Src.source.pipeline.service import create_service
    return create_service(warm=False).test_client()


@pytest.mark.parametrize("path", ["/compose", "/compose/quick", "/analyse", "/review"])
def test_every_endpoint_but_health_needs_the_token(locked, path):
    for headers in ({}, {"Authorization": "Bearer wrong"}, {"Authorization": "s3cret"}):
        r = locked.post(path, json={"message": MESSAGE}, headers=headers)
        assert r.status_code == 401 and r.get_json() == {"error": "unauthorized"}


def test_the_right_token_gets_through_and_health_stays_open(locked, fake):
    fake["answers"] = [_answer("Could you check the deck before Friday?")]
    fake["verdicts"] = [PASS]
    r = locked.post("/compose", json={"message": MESSAGE}, headers={"Authorization": "Bearer s3cret"})
    assert r.status_code == 200 and r.get_json()["rewrite"] == "Could you check the deck before Friday?"
    health = locked.get("/health")
    assert health.status_code == 200 and health.get_json()["token_required"] is True


def test_without_a_token_the_service_is_open_as_before(client, fake):
    assert client.post("/compose/quick", json={"message": MESSAGE}).status_code == 200
    assert client.get("/health").get_json()["token_required"] is False
