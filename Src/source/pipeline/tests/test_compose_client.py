"""Compose client tests. The HTTP call is always mocked."""
from __future__ import annotations

import json

import pytest

from Src.source.pipeline import compose_client, compose_prompt as cp

SIGNALS = [{"model": "tone", "label": "casual", "confidence": 0.9, "note": "x"}]


def _reply(content):
    return {"choices": [{"message": {"content": content}}]}


def test_sends_the_compose_prompt_with_thinking_off_and_the_schema(monkeypatch):
    sent = {}

    def fake_post(url, payload, timeout):
        sent.update(url=url, payload=payload)
        return _reply('{"rewrite": "Could you check it?", "notes": ["Made the ask direct."]}')

    monkeypatch.setattr(compose_client, "_post", fake_post)
    out = compose_client.complete("can u maybe check it", SIGNALS, few_shot=True)

    assert sent["url"].endswith("/v1/chat/completions")
    payload = sent["payload"]
    assert payload["messages"] == cp.build_messages("can u maybe check it", SIGNALS, few_shot=True)
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert payload["response_format"]["json_schema"]["schema"] == cp.RESPONSE_SCHEMA
    assert out["rewrite"] == "Could you check it?"
    assert out["notes"] == ["Made the ask direct."]


def test_unusable_reply_raises_output_error(monkeypatch):
    monkeypatch.setattr(compose_client, "_post", lambda *a: _reply("I'm not sure what you mean."))
    with pytest.raises(cp.ComposeOutputError):
        compose_client.complete("hi", None)


def test_odd_response_shape_raises_server_error(monkeypatch):
    monkeypatch.setattr(compose_client, "_post", lambda *a: {"error": "loading model"})
    with pytest.raises(compose_client.ComposeServerError, match="unexpected response shape"):
        compose_client.complete("hi", None)


def test_unreachable_server_is_a_server_error():
    with pytest.raises(compose_client.ComposeServerError, match="cannot reach"):
        compose_client.complete("hi", None, base_url="http://127.0.0.1:9", timeout=2)


def test_cli_records_errors_and_keeps_going(monkeypatch, tmp_path, capsys):
    replies = iter([_reply("nonsense"), _reply('{"rewrite": "Hi.", "notes": ["Kept it."]}')])
    monkeypatch.setattr(compose_client, "_post", lambda *a: next(replies))
    out = tmp_path / "out.jsonl"

    code = compose_client.main(["first", "second", "--out", str(out)])

    rows = [json.loads(l) for l in out.read_text().splitlines()]
    assert code == 0
    assert "error" in rows[0] and rows[1]["rewrite"] == "Hi."
    assert all(r["prompt"] == cp.fingerprint() for r in rows)
    assert "1/2 parsed" in capsys.readouterr().out
