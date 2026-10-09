"""Compose prompt tests. No model is called."""
from __future__ import annotations

import json

import pytest

from Src.source.pipeline import compose_prompt as cp
from Src.source.pipeline.contract import unavailable

SIGNALS = [
    {"model": "circa", "label": "indirect", "confidence": 0.41, "note": "p(indirect)=0.41"},
    {"model": "tone", "label": "casual", "confidence": 0.91, "note": "register reads as casual"},
    {"model": "politeness", "label": "high", "confidence": 0.555015197568389, "note": "score +0.7"},
]
MESSAGE = "no rush but could you maybe check the deck before Friday?"
MEANING = {"ask": "Check the deck", "deadline": "", "urgency": "low", "tone": "casual", "implied": ""}


# --------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------

def test_failed_signal_matches_production_stub():
    """Training must show a failure exactly as the adapters return one."""
    stub = unavailable("tone")
    assert cp.failed_signal("tone") == {
        "model": stub["model"], "label": stub["label"], "confidence": stub["confidence"],
    }


def test_clean_signals_fixed_order_and_no_note():
    out = cp.clean_signals(SIGNALS)
    assert [s["model"] for s in out] == list(cp.SIGNAL_ORDER)
    assert all(set(s) == {"model", "label", "confidence"} for s in out)
    assert out[1]["confidence"] == 0.555


@pytest.mark.parametrize("bad", [
    {"model": "tone", "label": "unavailable", "confidence": None},   # old data scripts
    {"model": "tone", "label": "unknown", "confidence": 0.0},        # production stub
    {"model": "tone"},
])
def test_any_failure_shape_becomes_the_production_one(bad):
    out = cp.clean_signals([bad])
    assert out[0] == cp.failed_signal("tone")


def test_missing_classifiers_are_filled_in_as_failed():
    out = cp.clean_signals([])
    assert out == [cp.failed_signal(m) for m in cp.SIGNAL_ORDER]


# --------------------------------------------------------------------------
# Prompt
# --------------------------------------------------------------------------

def test_user_prompt_is_deterministic():
    assert cp.user_prompt(MESSAGE, SIGNALS) == cp.user_prompt(MESSAGE, list(reversed(SIGNALS)))


def test_user_prompt_contents():
    text = cp.user_prompt(MESSAGE, SIGNALS)
    assert f"<message>\n{MESSAGE}\n</message>" in text
    assert "- tone: casual (0.91)" in text
    assert not any(s["note"] in text for s in SIGNALS)
    assert "<question>" not in text


def test_circa_reply_is_split_from_its_question():
    source = "Q: Are you free on Friday?\nReply: I'm away that week."
    assert cp.split_circa(source) == ("Are you free on Friday?", "I'm away that week.")
    text = cp.user_prompt(source, SIGNALS)
    assert "<question>\nAre you free on Friday?\n</question>" in text
    assert "<message>\nI'm away that week.\n</message>" in text


def test_non_circa_text_starting_with_q_is_left_alone():
    assert cp.split_circa("Q: what time?") == (None, "Q: what time?")


def test_zero_shot_has_no_examples():
    messages = cp.build_messages(MESSAGE, SIGNALS)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "<message>" not in messages[0]["content"]


def test_few_shot_interleaves_every_example():
    messages = cp.build_messages(MESSAGE, SIGNALS, few_shot=True)
    n = len(cp.examples())
    assert len(messages) == 2 + 2 * n
    assert [m["role"] for m in messages[1:-1]] == ["user", "assistant"] * n
    assert messages[-1]["content"] == cp.user_prompt(MESSAGE, SIGNALS)


def test_one_output_format_meaning_first():
    """Teacher, baseline and fine-tuned model all answer {"meaning", "rewrite",
    "notes"} in that order - meaning first, so it is worked out before the rewrite."""
    assert '"meaning"' in cp.system_prompt()
    assert list(cp.RESPONSE_SCHEMA["properties"]) == ["meaning", "rewrite", "notes"]
    messages = cp.build_messages(MESSAGE, SIGNALS, few_shot=True)
    for m in messages:
        if m["role"] == "assistant":
            assert list(json.loads(m["content"])) == ["meaning", "rewrite", "notes"]


def test_system_prompt_carries_the_nd_rules():
    text = cp.system_prompt().lower()
    for phrase in ("ask first", "bullet points", "literal words", "rough notes",
                   "do not guess", "clear is not blunt"):
        assert phrase in text, phrase


def test_fingerprint_is_stable():
    assert cp.fingerprint() == cp.fingerprint()
    assert len(cp.fingerprint()) == 12


# --------------------------------------------------------------------------
# Examples obey the style guide - they are what the baseline imitates
# --------------------------------------------------------------------------

@pytest.mark.parametrize("ex", cp.examples(), ids=lambda e: e["id"])
def test_example_follows_the_contract(ex):
    parsed = cp.parse_response(cp.assistant_response(ex))
    assert 1 <= len(parsed["notes"]) <= 3
    assert all(len(n.split()) < 20 for n in parsed["notes"])
    _q, message = cp.split_circa(ex["source"])
    ratio = len(ex["rewrite"].split()) / len(message.split())
    assert 0.5 <= ratio <= 2.5
    if parsed["notes"] == [cp.ALREADY_CLEAR_NOTE]:
        assert ex["rewrite"] == ex["source"]


def test_examples_cover_the_cases_that_matter():
    ids = {e["id"] for e in cp.examples()}
    assert {"example_already_clear", "example_circa_reply", "example_rough_notes",
            "example_several_asks", "example_idioms"} <= ids
    assert any(s["label"] == "unknown" for e in cp.examples() for s in e["signals"])


def test_bullet_example_uses_the_bullet_format():
    ex = {e["id"]: e for e in cp.examples()}["example_several_asks"]
    assert [line for line in ex["rewrite"].splitlines() if line.startswith("- ")]


def test_missing_information_goes_in_a_note_not_the_rewrite():
    """Rough notes that leave something out get a note asking for it - never a guess."""
    ex = {e["id"]: e for e in cp.examples()}["example_rough_notes"]
    assert "thing" not in ex["rewrite"]
    assert any("thing" in n for n in ex["notes"])


@pytest.mark.parametrize("ex", cp.examples(), ids=lambda e: e["id"])
def test_example_passes_the_training_filter(ex):
    """If our own examples fail the filter, the model learns to fail it."""
    pytest.importorskip("spacy")
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data_prep"))
    try:
        import filter_pairs as fp
        fp.nlp()
    except OSError:
        pytest.skip("en_core_web_sm not installed")
    record = {"source": ex["source"], "rewrite": ex["rewrite"], "notes": ex["notes"]}
    for check in (fp.check_notes, fp.check_dropped, fp.check_added, fp.check_length):
        assert check(record) is None, check.__name__


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def test_parse_tolerates_fences_and_chatter():
    body = json.dumps({"meaning": MEANING, "rewrite": " Hi. ", "notes": ["Kept it."]})
    reply = f"Sure!\n```json\n{body}\n```"
    assert cp.parse_response(reply) == {"meaning": MEANING, "rewrite": "Hi.", "notes": ["Kept it."]}


def test_parse_round_trips_the_training_target():
    for ex in cp.examples():
        assert cp.parse_response(cp.assistant_response(ex)) == {
            "meaning": ex["meaning"], "rewrite": ex["rewrite"], "notes": ex["notes"],
        }


@pytest.mark.parametrize("reply, reason", [
    ("no json here", "no JSON object"),
    ('{"rewrite": "x", "notes": [}', "not valid JSON"),
    ('{"notes": ["a"]}', "rewrite missing"),
    ('{"rewrite": "x", "notes": "a"}', "notes missing"),
    ('{"rewrite": "x", "notes": []}', "0 notes"),
    ('{"rewrite": "x", "notes": ["a", "b", "c", "d"]}', "4 notes"),
    ('{"rewrite": "x", "notes": ["a"]}', "meaning missing"),
])
def test_parse_rejects_with_a_reason(reply, reason):
    with pytest.raises(cp.ComposeOutputError, match=reason):
        cp.parse_response(reply)


def test_parse_checks_meaning():
    good = {"meaning": dict(MEANING), "rewrite": "x", "notes": ["a"]}
    assert cp.parse_response(json.dumps(good))["meaning"]["urgency"] == "low"
    good["meaning"]["urgency"] = "urgent"
    with pytest.raises(cp.ComposeOutputError, match="urgency"):
        cp.parse_response(json.dumps(good))
