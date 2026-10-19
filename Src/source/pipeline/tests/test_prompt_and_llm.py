"""Prompt builder and LLM tests. The LLM transport is always mocked."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from Src.source.pipeline.analysis import analyse
from Src.source.pipeline.config import LLMConfig, load
from Src.source.pipeline.llm import LLMError, LLMResult, complete
from Src.source.pipeline.pipeline import run
from Src.source.pipeline.prompt import RESPONSE_SCHEMA, build

MESSAGE = "Could you send the report to the client by Friday? It's urgent."


@pytest.fixture(scope="module")
def analysis():
    return analyse(MESSAGE)


# --------------------------------------------------------------------------
# Prompt
# --------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["review", "form"])
def test_both_templates_render(analysis, mode):
    text = build(analysis, mode)
    assert MESSAGE in text


@pytest.mark.parametrize("mode", ["review", "form"])
def test_no_placeholder_is_left_unfilled(analysis, mode):
    """A template placeholder that survives rendering would reach the model."""
    import re
    text = build(analysis, mode)
    leftovers = re.findall(r"\{[a-z_]+\}", text)
    assert not leftovers, f"unfilled placeholders: {leftovers}"


def test_unknown_mode_is_rejected(analysis):
    with pytest.raises(ValueError, match="unknown mode"):
        build(analysis, "sideways")


def test_prompt_carries_spans_the_llm_can_cite(analysis):
    text = build(analysis, "review")
    for item in analysis.extraction.found.values():
        assert f"span=[{item.span[0]}, {item.span[1]}]" in text


def test_prompt_states_the_missing_fields(analysis):
    text = build(analysis, "review")
    for name in analysis.extraction.missing:
        assert name in text


def test_comments_carry_confidence_and_weighing_instruction(analysis):
    config = replace(load(), include_model_comments=True)
    text = build(analysis, "review", config)
    assert "confidence" in text.lower()
    assert "0.3 is a hint" in text  # the instruction to discount low confidence


def test_the_flag_removes_every_comment(analysis):
    on = build(analysis, "review", replace(load(), include_model_comments=True))
    off = build(analysis, "review", replace(load(), include_model_comments=False))
    assert "WHAT THREE SMALL MODELS SAID" in on
    assert "WHAT THREE SMALL MODELS SAID" not in off
    for comment in analysis.comments:
        if comment["confidence"] > 0:
            assert str(comment["note"]) not in off


def test_with_and_without_differ_only_by_the_comment_block(analysis):
    """The A/B has to be fair: nothing else may change between the two runs."""
    on = build(analysis, "review", replace(load(), include_model_comments=True))
    off = build(analysis, "review", replace(load(), include_model_comments=False))
    start = on.index("WHAT THREE SMALL MODELS SAID")
    end = on.index("Return JSON matching")
    assert on[:start].rstrip() == off[:off.index("Return JSON matching")].rstrip()
    assert on[end:] == off[off.index("Return JSON matching"):]


def test_unavailable_models_are_omitted_not_shown_as_noise(analysis):
    text = build(analysis, "review", replace(load(), include_model_comments=True))
    assert "model unavailable" not in text


def test_schema_requires_a_quote_and_a_hint_on_every_claim():
    """The model quotes and estimates; the validator computes the real span."""
    claim = RESPONSE_SCHEMA["properties"]["claims"]["items"]
    assert "text" in claim["required"]
    assert "span_hint" in claim["required"]
    assert "span" not in claim["required"], "the model must not supply exact offsets"
    assert claim["additionalProperties"] is False


# --------------------------------------------------------------------------
# LLM - transport always mocked, never a live endpoint
# --------------------------------------------------------------------------

GOOD_JSON = json.dumps({"summary": "ok", "claims": [], "unstated": []})


def test_parses_a_good_response():
    result = complete("prompt", LLMConfig(), caller=lambda p, c: GOOD_JSON)
    assert isinstance(result, LLMResult)
    assert result.data["summary"] == "ok"
    assert result.attempts == 1


def test_retries_once_on_malformed_json_then_succeeds():
    calls = []

    def flaky(_prompt, _config):
        calls.append(1)
        return "not json{" if len(calls) == 1 else GOOD_JSON

    result = complete("prompt", LLMConfig(), caller=flaky)
    assert result.attempts == 2
    assert len(calls) == 2


def test_gives_up_after_the_retry():
    calls = []

    def always_bad(_prompt, _config):
        calls.append(1)
        return "{{{"

    with pytest.raises(LLMError, match="no parseable JSON"):
        complete("prompt", LLMConfig(), caller=always_bad)
    assert len(calls) == 2  # one attempt plus one retry, not more


def test_retry_count_is_configurable():
    calls = []

    def always_bad(_prompt, _config):
        calls.append(1)
        return "nope"

    with pytest.raises(LLMError):
        complete("prompt", LLMConfig(json_retries=3), caller=always_bad)
    assert len(calls) == 4


def test_json_that_is_not_an_object_is_treated_as_malformed():
    with pytest.raises(LLMError):
        complete("prompt", LLMConfig(), caller=lambda p, c: "[1, 2, 3]")


def test_transport_failure_does_not_leak_the_prompt():
    secret = "Ship the Acme contract to Dana by Friday."

    def boom(_prompt, _config):
        raise ConnectionError(secret)

    with pytest.raises(LLMError) as excinfo:
        complete(secret, LLMConfig(), caller=boom)
    assert secret not in str(excinfo.value)
    assert "ConnectionError" in str(excinfo.value)


def test_model_and_endpoint_come_from_config():
    config = LLMConfig(model="some-other-model", base_url="https://proxy.internal")
    result = complete("p", config, caller=lambda p, c: GOOD_JSON)
    assert result.model == "some-other-model"


# --------------------------------------------------------------------------
# End to end, mocked
# --------------------------------------------------------------------------

def test_clean_llm_response_survives_end_to_end():
    start = MESSAGE.index("Friday")
    payload = json.dumps({
        "summary": "A request with a Friday deadline.",
        "claims": [{"field": "deadline", "text": "Friday",
                    "span": [start, start + 6], "reading": "the stated deadline"}],
        "unstated": ["Who exactly should send it?"],
    })
    out = run(MESSAGE, "review", llm=lambda p, c: payload)
    assert out["degraded"] is False
    assert out["llm_attempts"] == 1


def test_invented_date_degrades_end_to_end():
    """The brief's named case, through the whole pipeline."""
    payload = json.dumps({
        "summary": "They need this by Tuesday.", "claims": [], "unstated": [],
    })
    out = run(MESSAGE, "review", llm=lambda p, c: payload)
    assert out["degraded"] is True
    assert any("DATE" in r for r in out["degraded_reason"])


def test_unreachable_llm_degrades_rather_than_raising():
    def dead(_prompt, _config):
        raise ConnectionError("no route to host")

    out = run(MESSAGE, "review", llm=dead)
    assert out["degraded"] is True
    assert out["llm_attempts"] == 0
    assert out["claims"], "should still show what the extractor found"


def test_degraded_output_still_carries_verified_spans():
    out = run(MESSAGE, "review", llm=lambda p, c: "garbage")
    assert out["degraded"] is True
    for claim in out["claims"]:
        start, end = claim["span"]
        assert MESSAGE[start:end] == claim["text"]


# --------------------------------------------------------------------------
# Provider switching (Kimi via the OpenAI-compatible path, or Anthropic)
# --------------------------------------------------------------------------

def test_each_provider_has_a_complete_default_set():
    """Asserts the shipped defaults, not whatever the local .env happens to
    say. An earlier version of this test read load() and broke the moment a
    developer set PIPELINE_LLM_PROVIDER - a test that depends on local
    configuration reports the machine, not the code."""
    from Src.source.pipeline.config import PROVIDER_DEFAULTS
    for name, spec in PROVIDER_DEFAULTS.items():
        assert spec["model"], f"{name} has no default model"
        assert spec["key_env"], f"{name} names no key variable"
    assert PROVIDER_DEFAULTS["openai"]["model"] == "kimi-k3"
    assert PROVIDER_DEFAULTS["openai"]["base_url"] == "https://api.moonshot.ai/v1"
    assert PROVIDER_DEFAULTS["openai"]["key_env"] == "MOONSHOT_API_KEY"
    assert PROVIDER_DEFAULTS["nvidia"]["model"] == "moonshotai/kimi-k3"


def test_config_honours_the_provider_environment_variable(monkeypatch):
    """An explicit environment variable must beat whatever .env says.

    Deliberately no importlib.reload: default_factory means a fresh
    LLMConfig() already re-reads the environment, and reloading the module
    re-runs _load_env_files(), which puts the developer's own .env values
    back and makes the test report the machine instead of the code. This
    test broke exactly that way once the .env here gained a model override.
    """
    from Src.source.pipeline.config import LLMConfig

    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("PIPELINE_LLM_MODEL", "claude-opus-5")
    cfg = LLMConfig()
    assert cfg.provider == "anthropic"
    assert cfg.model == "claude-opus-5"


def test_the_provider_default_applies_when_no_model_is_named(monkeypatch):
    """Switching provider alone should carry its own model and endpoint."""
    from Src.source.pipeline.config import LLMConfig

    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "nvidia")
    monkeypatch.delenv("PIPELINE_LLM_MODEL", raising=False)
    monkeypatch.delenv("PIPELINE_LLM_BASE_URL", raising=False)
    cfg = LLMConfig()
    assert cfg.model == "moonshotai/kimi-k3"
    assert cfg.base_url == "https://integrate.api.nvidia.com/v1"


def test_no_test_depends_on_the_local_env_file():
    """Guard against the class of failure above: a test that reads .env
    reports the developer's machine, not the code."""
    import pathlib as _p
    for path in _p.Path("Src/source/pipeline/tests").glob("test_*.py"):
        source = path.read_text()
        # Assembled at runtime so this file does not match its own guard.
        needle = "importlib." + "reload(config"
        assert needle not in source, (
            f"{path.name} reloads config, which re-reads .env and makes the "
            f"test report the developer's machine instead of the code")


# --------------------------------------------------------------------------
# Regressions from benchmarking llama-3.2-11b on NVIDIA
# --------------------------------------------------------------------------

def test_markdown_fenced_json_is_accepted():
    """NVIDIA enforces json_schema for kimi-k3 but not for llama-3.2-11b,
    which fences the same request's output. Perfectly good JSON otherwise."""
    fenced = '```json\n{"summary": "ok", "claims": [], "unstated": []}\n```'
    assert complete("p", LLMConfig(), caller=lambda p, c: fenced).data["summary"] == "ok"


def test_prose_before_the_object_is_tolerated():
    messy = 'Here is the analysis:\n{"summary": "ok", "claims": [], "unstated": []}'
    assert complete("p", LLMConfig(), caller=lambda p, c: messy).data["summary"] == "ok"


def test_a_missing_required_key_is_filled_not_rejected():
    """llama-3.2-11b returned claims and unstated but no summary. Throwing
    away valid claims over a missing summary would be the wrong trade."""
    partial = '{"claims": [], "unstated": ["Who should act?"]}'
    data = complete("p", LLMConfig(), caller=lambda p, c: partial).data
    assert data["summary"] == ""
    assert data["unstated"] == ["Who should act?"]


def test_genuinely_broken_json_still_fails():
    with pytest.raises(LLMError):
        complete("p", LLMConfig(), caller=lambda p, c: "```json\nnot json{\n```")


# --------------------------------------------------------------------------
# Input size guard
# --------------------------------------------------------------------------

def test_an_over_long_message_is_rejected_before_any_llm_call():
    """The pipeline spends the money, so it guards itself - it is reachable
    without passing through the Flask route that also checks."""
    called = []

    def transport(p, c):
        called.append(1)
        return GOOD_JSON

    cfg = load()
    out = run("x" * (cfg.max_message_chars + 1), "review", cfg, llm=transport)
    assert out["degraded"] is True
    assert not called, "an over-long message must not reach the model"
    assert "limit is" in out["degraded_reason"][0]


def test_the_rejection_has_the_same_shape_as_every_other_return():
    cfg = load()
    out = run("x" * (cfg.max_message_chars + 1), "review", cfg,
              llm=lambda p, c: GOOD_JSON)
    for key in ("degraded", "cross_check", "claims", "llm_attempts", "model"):
        assert key in out


def test_the_rejection_reports_length_not_content():
    cfg = load()
    secret = "Acme-Vertex " * 1000
    out = run(secret, "review", cfg, llm=lambda p, c: GOOD_JSON)
    assert "Acme-Vertex" not in " ".join(out["degraded_reason"])


def test_a_message_at_the_limit_is_still_processed():
    cfg = load()
    called = []
    run("x " * (cfg.max_message_chars // 2), "review", cfg,
        llm=lambda p, c: (called.append(1), GOOD_JSON)[1])
    assert called, "a message within the limit must reach the model"


def test_the_pipeline_limit_matches_the_deployed_api():
    """Two limits that disagree would mean the API accepts what the pipeline
    rejects, or vice versa.

    Skipped where the API source is not present. The inference deploy ships
    only the pipeline, its models and the one backend module the extractor
    needs - not the Flask routes - so this cross-component check can only run
    from a full checkout. It does run in CI, which is where a drift between
    the two constants would actually be introduced.
    """
    import re, pathlib
    route = pathlib.Path("backend/app/routes/decode.py")
    if not route.is_file():
        pytest.skip("API source not present - this is a full-checkout check")
    api_limit = int(re.search(r"MAX_MESSAGE_LENGTH\s*=\s*(\d+)",
                              route.read_text()).group(1))
    assert load().max_message_chars == api_limit


# --------------------------------------------------------------------------
# Provider wiring (restored - an earlier edit sliced these out)
# --------------------------------------------------------------------------

def test_every_provider_has_a_transport():
    from Src.source.pipeline.config import PROVIDER_DEFAULTS
    from Src.source.pipeline.llm import TRANSPORTS
    assert set(TRANSPORTS) == {"openai", "nvidia", "groq", "anthropic"}
    assert set(PROVIDER_DEFAULTS) <= set(TRANSPORTS), \
        "a provider with no transport would fail only at call time"


def test_nvidia_and_moonshot_are_separate_endpoints():
    """A key for one sent to the other fails as AuthenticationError, which
    reads like a bad key rather than a wrong address. Cost a round trip once."""
    from Src.source.pipeline.config import PROVIDER_DEFAULTS
    nv, ms = PROVIDER_DEFAULTS["nvidia"], PROVIDER_DEFAULTS["openai"]
    assert nv["base_url"] != ms["base_url"]
    assert nv["key_env"] == "NVIDIA_API_KEY"
    assert nv["model"].startswith("moonshotai/"), "NVIDIA uses vendor prefixes"
    assert not ms["model"].startswith("moonshotai/"), "Moonshot does not"


def test_streaming_is_on_by_default():
    """Reasoning models can take minutes to first byte; a non-streaming
    request just holds an open socket until something times out."""
    assert LLMConfig().stream is True


def test_response_format_can_be_stepped_down_without_a_code_change():
    """Not every OpenAI-compatible endpoint enforces strict schemas."""
    assert LLMConfig().response_format == "json_schema"
    assert LLMConfig(response_format="json_object").response_format == "json_object"


def test_a_malformed_numeric_setting_falls_back_instead_of_crashing(monkeypatch, capsys):
    """A stray character in a .env took down 46 tests and would have stopped
    the inference service booting, with a ValueError naming no variable."""
    from Src.source.pipeline.config import LLMConfig
    monkeypatch.setenv("PIPELINE_LLM_TIMEOUT", "900v")
    cfg = LLMConfig()
    assert cfg.timeout_seconds == 600.0
    assert "PIPELINE_LLM_TIMEOUT" in capsys.readouterr().err


def test_a_valid_numeric_setting_is_still_honoured(monkeypatch):
    from Src.source.pipeline.config import LLMConfig
    monkeypatch.setenv("PIPELINE_LLM_TIMEOUT", "123")
    assert LLMConfig().timeout_seconds == 123.0


# --------------------------------------------------------------------------
# Shape coercion - endpoints do not all enforce the schema they are given
# --------------------------------------------------------------------------

def test_a_summary_returned_as_a_list_is_joined():
    """Observed live: llama returned summary as two sentences in an array,
    which the frontend would have rendered with brackets and quotes."""
    payload = json.dumps({"summary": ["First sentence.", "Second sentence."],
                          "claims": [], "unstated": []})
    data = complete("p", LLMConfig(), caller=lambda p, c: payload).data
    assert data["summary"] == "First sentence. Second sentence."


def test_a_single_item_where_a_list_was_asked_for_is_wrapped():
    payload = json.dumps({"summary": "ok", "claims": [], "unstated": "One question?"})
    assert complete("p", LLMConfig(), caller=lambda p, c: payload).data["unstated"] \
        == ["One question?"]


def test_unstated_entries_are_plain_strings():
    payload = json.dumps({"summary": "ok", "claims": [],
                          "unstated": ["  spaced  ", "", "real question?"]})
    out = complete("p", LLMConfig(), caller=lambda p, c: payload).data["unstated"]
    assert out == ["spaced", "real question?"]


def test_a_well_formed_response_is_untouched():
    payload = json.dumps({"summary": "A summary.", "claims": [],
                          "unstated": ["A question?"]})
    data = complete("p", LLMConfig(), caller=lambda p, c: payload).data
    assert data["summary"] == "A summary." and data["unstated"] == ["A question?"]


# --------------------------------------------------------------------------
# Groq, and the retries that let every request end in an answer
# --------------------------------------------------------------------------

def test_groq_carries_its_own_model_endpoint_and_effort(monkeypatch):
    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    for name in ("PIPELINE_LLM_MODEL", "PIPELINE_LLM_BASE_URL", "PIPELINE_LLM_REASONING_EFFORT"):
        monkeypatch.delenv(name, raising=False)
    cfg = LLMConfig()
    assert cfg.model == "openai/gpt-oss-120b"
    assert cfg.base_url == "https://api.groq.com/openai/v1"
    assert cfg.reasoning_effort == "low"
    assert cfg.api_key == "gsk_test"


def test_groq_never_borrows_another_providers_key(monkeypatch):
    """The inference host also holds an NVIDIA key. A missing Groq key must
    fail as missing, not send someone else's key to Groq."""
    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-not-for-groq")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-not-for-groq")
    assert LLMConfig().api_key == ""


def test_kimi_providers_send_no_reasoning_effort(monkeypatch):
    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "nvidia")
    monkeypatch.delenv("PIPELINE_LLM_REASONING_EFFORT", raising=False)
    assert LLMConfig().reasoning_effort is None


def _fake_openai(monkeypatch):
    """Stand in for the SDK client and record what each request asked for."""
    from types import SimpleNamespace
    from Src.source.pipeline import llm

    sent = []

    def create(**request):
        sent.append(request)
        message = SimpleNamespace(content=GOOD_JSON)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(llm, "_openai_client", lambda config: client)
    return sent


@pytest.mark.parametrize("effort", [None, "low"])
def test_reasoning_effort_is_sent_only_when_set(monkeypatch, effort):
    from Src.source.pipeline.llm import _call_openai
    sent = _fake_openai(monkeypatch)
    _call_openai("p", LLMConfig(reasoning_effort=effort, stream=False))
    assert sent[0].get("reasoning_effort") == effort
    assert ("reasoning_effort" in sent[0]) is (effort is not None)


def test_a_failed_request_is_sent_once_more():
    """Groq answers 400 when the output breaks the strict schema; sent
    again, it passed every time it was measured."""
    calls = []

    def flaky(_prompt, _config):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("json_validate_failed")
        return GOOD_JSON

    result = complete("p", LLMConfig(), caller=flaky)
    assert result.data["summary"] == "ok"
    assert result.attempts == 2


def test_a_refused_key_is_not_sent_again():
    class Unauthorised(Exception):
        status_code = 401

    calls = []

    def refused(_prompt, _config):
        calls.append(1)
        raise Unauthorised()

    with pytest.raises(LLMError, match="Unauthorised"):
        complete("p", LLMConfig(), caller=refused)
    assert len(calls) == 1


# --------------------------------------------------------------------------
# Repair: a failed answer goes back to the model with what failed
# --------------------------------------------------------------------------

FRIDAY = MESSAGE.index("Friday")
INVENTED = json.dumps({
    "summary": "They need this by Tuesday.",
    "claims": [{"field": "deadline", "text": "Friday", "span_hint": FRIDAY,
                "reading": "the day it is due"}],
    "unstated": [], "missing": [],
})
CLEAN = json.dumps({
    "summary": "A request with a Friday deadline.",
    "claims": [{"field": "deadline", "text": "Friday", "span_hint": FRIDAY,
                "reading": "the day it is due"}],
    "unstated": [], "missing": [],
})


def test_a_failed_answer_is_repaired_with_what_failed():
    prompts = []

    def model(prompt, _config):
        prompts.append(prompt)
        return INVENTED if len(prompts) == 1 else CLEAN

    out = run(MESSAGE, "review", llm=model)
    assert out["degraded"] is False and "partial" not in out
    assert out["summary"] == "A request with a Friday deadline."
    assert out["repairs"] == 1 and out["llm_attempts"] == 2
    assert prompts[1].startswith(prompts[0]), "the repair extends the prompt"
    note = prompts[1][len(prompts[0]):]
    assert "'Tuesday' - a date the message does not contain" in note
    assert "They need this by Tuesday." in note, "the failed answer is shown back"


def test_repairs_stop_at_the_configured_count_then_salvage():
    calls = []

    def stubborn(_prompt, _config):
        calls.append(1)
        return INVENTED

    out = run(MESSAGE, "review", replace(load(), repair_attempts=2), llm=stubborn)
    assert len(calls) == 3, "one answer and two repairs, no more"
    assert out["degraded"] is False and out["partial"] is True
    assert out["summary"] == "" and [c["text"] for c in out["claims"]] == ["Friday"]


def test_no_repair_starts_that_would_overrun_the_time_budget():
    calls = []

    def model(_prompt, _config):
        calls.append(1)
        return INVENTED

    run(MESSAGE, "review", replace(load(), repair_budget_seconds=0.0), llm=model)
    assert len(calls) == 1


def test_a_clean_first_answer_costs_no_repair():
    calls = []

    def model(_prompt, _config):
        calls.append(1)
        return CLEAN

    out = run(MESSAGE, "review", llm=model)
    assert len(calls) == 1 and out["repairs"] == 0


def test_an_unreachable_repair_keeps_the_salvage():
    calls = []

    def dies_on_repair(_prompt, _config):
        calls.append(1)
        if len(calls) > 1:
            raise ConnectionError("gone")
        return INVENTED

    out = run(MESSAGE, "review", llm=dies_on_repair)
    assert out["degraded"] is False and out["partial"] is True
