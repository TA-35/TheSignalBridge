"""Span resolution and the LLM-vs-extractor cross-check."""
from __future__ import annotations

import json
from dataclasses import replace

import pytest

from Src.source.pipeline.analysis import analyse
from Src.source.pipeline.config import load
from Src.source.pipeline.crosscheck import compare
from Src.source.pipeline.pipeline import run
from Src.source.pipeline.prompt import build
from Src.source.pipeline.validator import resolve_span, validate_response

REPEATED = (
    "Please let us know your availability.\n\n"
    "Please let us know your preferred slots.\n\n"
    "Send it by Friday."
)


# --------------------------------------------------------------------------
# resolve_span - the bug that made my first design wrong
# --------------------------------------------------------------------------

def test_a_unique_quote_resolves_without_a_hint():
    assert resolve_span(REPEATED, "Send it by Friday") is not None


def test_a_repeated_quote_is_refused_when_there_is_no_hint():
    """find() would silently return the first match and highlight the wrong
    paragraph. Refusing is the only safe answer."""
    assert REPEATED.count("Please let us know") == 2
    assert resolve_span(REPEATED, "Please let us know") is None


def test_a_hint_picks_the_intended_occurrence():
    second = REPEATED.rfind("Please let us know")
    span = resolve_span(REPEATED, "Please let us know", hint=second + 3)
    assert span is not None and span[0] == second


def test_a_rough_hint_is_good_enough():
    """The model's arithmetic only has to be approximately right."""
    second = REPEATED.rfind("Please let us know")
    for error in (-12, -5, 0, 5, 12):
        span = resolve_span(REPEATED, "Please let us know", hint=second + error)
        assert span[0] == second


def test_a_quote_absent_from_the_message_is_refused():
    assert resolve_span(REPEATED, "Send it by Tuesday") is None


def test_resolved_spans_are_exact_by_construction():
    span = resolve_span(REPEATED, "Send it by Friday")
    assert REPEATED[span[0]:span[1]] == "Send it by Friday"


# --------------------------------------------------------------------------
# End to end with quoted claims
# --------------------------------------------------------------------------

MESSAGE = "Could you send the report to the client by Friday? It's urgent."


def test_a_quoting_llm_response_validates():
    payload = json.dumps({
        "summary": "A request with a Friday deadline.",
        "claims": [{"field": "deadline", "text": "Friday",
                    "span_hint": 40, "reading": "the stated deadline"}],
        "unstated": [],
    })
    out = run(MESSAGE, "review", llm=lambda p, c: payload)
    assert out["degraded"] is False
    span = out["claims"][0]["span"]
    assert MESSAGE[span[0]:span[1]] == "Friday"


def test_a_wildly_wrong_hint_still_resolves_when_the_quote_is_unique():
    payload = json.dumps({
        "summary": "ok",
        "claims": [{"field": "deadline", "text": "Friday",
                    "span_hint": 9999, "reading": "deadline"}],
        "unstated": [],
    })
    out = run(MESSAGE, "review", llm=lambda p, c: payload)
    assert out["degraded"] is False


def test_a_quote_the_message_lacks_degrades():
    payload = json.dumps({
        "summary": "ok",
        "claims": [{"field": "deadline", "text": "Tuesday",
                    "span_hint": 40, "reading": "deadline"}],
        "unstated": [],
    })
    out = run(MESSAGE, "review", llm=lambda p, c: payload)
    assert out["degraded"] is True


# --------------------------------------------------------------------------
# Cross-check
# --------------------------------------------------------------------------

def test_agreement_when_both_read_the_same_deadline():
    analysis = analyse(MESSAGE)
    start = MESSAGE.index("Friday")
    result = compare(
        [{"field": "deadline", "text": "Friday", "span": [start, start + 6]}],
        analysis)
    assert result.comparisons[0].verdict == "agree"
    assert result.agreement_rate == 1.0


def test_disagreement_is_surfaced_not_silently_resolved():
    """The entity check cannot catch this: 'report' is really in the message,
    just not the deadline."""
    analysis = analyse(MESSAGE)
    start = MESSAGE.index("report")
    result = compare(
        [{"field": "deadline", "text": "report", "span": [start, start + 6]}],
        analysis)
    assert result.comparisons[0].verdict == "disagree"
    assert "deadline" in [c.field for c in result.disagreements]


def test_overlapping_but_unequal_spans_count_as_agreement():
    """The two methods bracket clauses differently by design."""
    analysis = analyse(MESSAGE)
    action = analysis.extraction.actions[0]
    wider = [max(0, action.span[0] - 4), action.span[1]]
    result = compare(
        [{"field": "required_action", "text": MESSAGE[wider[0]:wider[1]],
          "span": wider}], analysis)
    assert result.comparisons[0].verdict == "agree"


def test_the_pipeline_always_reports_a_cross_check():
    payload = json.dumps({"summary": "ok", "claims": [], "unstated": []})
    out = run(MESSAGE, "review", llm=lambda p, c: payload)
    assert "cross_check" in out
    assert "agreement_rate" in out["cross_check"]


# --------------------------------------------------------------------------
# The second experiment axis
# --------------------------------------------------------------------------

def test_the_flag_removes_the_extracted_spans_from_the_prompt():
    analysis = analyse(MESSAGE)
    with_ = build(analysis, "review", replace(load(), include_extracted_spans=True))
    without = build(analysis, "review", replace(load(), include_extracted_spans=False))
    assert "span=[" in with_
    assert "span=[" not in without
    assert "read the message yourself" in without


def test_both_axes_are_independent():
    analysis = analyse(MESSAGE)
    base = load()
    seen = set()
    for spans in (True, False):
        for comments in (True, False):
            cfg = replace(base, include_extracted_spans=spans,
                          include_model_comments=comments)
            seen.add(build(analysis, "review", cfg))
    assert len(seen) == 4, "the two flags must produce four distinct prompts"


# --------------------------------------------------------------------------
# Regression from the first real K3 run: unconstrained field names
# --------------------------------------------------------------------------

def test_the_schema_constrains_field_to_our_own_names():
    """K3 invented "request" and "status" when `field` was a free string.
    Those match nothing the extractor emits, so every cross-check compared
    zero fields and reported agreement=None - indistinguishable from
    agreement, which is the worst way for a check to fail."""
    from Src.source.pipeline.analysis import FIELDS
    from Src.source.pipeline.prompt import RESPONSE_SCHEMA
    field = RESPONSE_SCHEMA["properties"]["claims"]["items"]["properties"]["field"]
    assert field.get("enum") == list(FIELDS)


def test_a_cross_check_over_unknown_field_names_reports_no_agreement():
    """Documents the failure mode so it is recognisable if it recurs."""
    analysis = analyse(MESSAGE)
    result = compare(
        [{"field": "status", "text": "Friday", "span": [40, 46]}], analysis)
    assert result.agreement_rate is None
    assert all(c.verdict in {"llm_only", "extractor_only"}
               for c in result.comparisons)


def test_a_degraded_response_reports_no_cross_check_agreement():
    """Degraded output is the extractor's own claims. Comparing it against
    the extractor reports 1.0 while comparing nothing - observed live on a
    llama-3.2-11b response that had actually failed validation."""
    out = run(MESSAGE, "review", llm=lambda p, c: "not json at all")
    assert out["degraded"] is True
    assert out["cross_check"]["agreement_rate"] is None
    assert "skipped" in out["cross_check"]


def test_an_undegraded_response_still_reports_agreement():
    start = MESSAGE.index("Friday")
    payload = json.dumps({
        "summary": "ok",
        "claims": [{"field": "deadline", "text": "Friday",
                    "span_hint": start, "reading": "deadline"}],
        "unstated": [],
    })
    out = run(MESSAGE, "review", llm=lambda p, c: payload)
    assert out["degraded"] is False
    assert out["cross_check"]["agreement_rate"] == 1.0


@pytest.mark.parametrize("transport,label", [
    (lambda p, c: "not json at all", "unparseable"),
    (lambda p, c: (_ for _ in ()).throw(ConnectionError("down")), "unreachable"),
    (lambda p, c: json.dumps({"summary": "by Tuesday", "claims": [],
                              "unstated": []}), "invented entity"),
])
def test_every_return_path_has_the_same_shape(transport, label):
    """Three ways to degrade. A frontend must not need to know which."""
    out = run(MESSAGE, "review", llm=transport)
    for key in ("degraded", "cross_check", "claims", "llm_attempts", "model"):
        assert key in out, f"{label} path is missing {key}"
    assert out["cross_check"]["agreement_rate"] is None
