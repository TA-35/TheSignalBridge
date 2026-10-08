"""Tests for the shared flag rule.

The important one is the regression test: moving the rule out of the Enron
and Stanford scripts must not change a single flag on data already selected
with the old copies.
"""
import json
import re
from pathlib import Path

import pytest

from Src.source.data_prep import flag_rule as fr

REPO = Path(__file__).resolve().parents[4]

# Selected with the old in-script copies; each must still hit its targets.
FINISHED = {
    "data/source/enron_source.jsonl": (fr.N_SRC_FLAGGED, fr.N_SRC_CLEAR),
    "data/gold/enron_gold.jsonl": (fr.N_GOLD_FLAGGED, fr.N_GOLD_CLEAR),
    "data/source/stanford_source.jsonl": (fr.N_SRC_FLAGGED, fr.N_SRC_CLEAR),
    "data/gold/stanford_gold.jsonl": (fr.N_GOLD_FLAGGED, fr.N_GOLD_CLEAR),
    "data/step1/stanford/gold_reserve.jsonl": (fr.N_RES_FLAGGED, fr.N_RES_CLEAR),
}


def _rows(rel):
    path = REPO / rel
    if not path.exists():
        pytest.skip(f"{rel} not in this checkout")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _old_is_flagged(r):
    """The rule exactly as it was copied in enron_step1.py and stanford_step1.py."""
    if fr.HEDGES.search(str(r.get("source", ""))):
        return True
    return any(s["model"] in fr.FLAG_RULES and str(s["label"]).lower() in fr.FLAG_RULES[s["model"]]
               for s in r["signals"])


@pytest.mark.parametrize("rel", FINISHED, ids=lambda p: Path(p).stem)
def test_finished_files_still_hit_their_targets(rel):
    assert fr.split_counts(_rows(rel)) == FINISHED[rel]


@pytest.mark.parametrize("rel", FINISHED, ids=lambda p: Path(p).stem)
def test_same_flag_as_the_old_copies_on_every_record(rel):
    rows = _rows(rel)
    changed = [r["id"] for r in rows if fr.is_flagged(r) != _old_is_flagged(r)]
    assert changed == []


def test_rule_is_defined_once():
    """No step-1 script keeps its own copy any more - that is how they drift."""
    defs = [p for p in (REPO / "Src").rglob("*.py")
            if p.name != "flag_rule.py" and "__pycache__" not in p.parts
            and re.search(r"^(FLAG_RULES|HEDGES)\s*=", p.read_text(), re.M)]
    assert defs == []


def _rec(source, **labels):
    sig = {"tone": "neutral", "politeness": "medium", "circa": "direct", **labels}
    return {"source": source,
            "signals": [{"model": m, "label": l, "confidence": 0.5} for m, l in sig.items()]}


def test_reasons():
    assert fr.flag_reasons(_rec("Please send the deck.")) == []
    assert fr.flag_reasons(_rec("Just wondering if you got it", politeness="high")) == [
        "hedge", "politeness=high"]
    assert fr.flag_reasons(_rec("Send it.", circa="indirect")) == ["circa=indirect"]


def test_tone_never_flags():
    for label in ("casual", "formal", "neutral"):
        assert not fr.is_flagged(_rec("Send it.", tone=label))


def test_failed_classifiers_do_not_flag():
    r = {"source": "Send it.",
         "signals": [{"model": m, "label": "unknown", "confidence": 0.0}
                     for m in ("tone", "politeness", "circa")]}
    assert not fr.is_flagged(r)


def test_circa_hedge_counts_only_in_the_reply():
    """The question is context, not rewritten, so its wording cannot flag."""
    in_question = _rec("Q: If you get a chance, are you free Friday?\nReply: No, I'm away.")
    in_reply = _rec("Q: Are you free Friday?\nReply: Just checking my calendar.")
    assert not fr.is_flagged(in_question)
    assert fr.flag_reasons(in_reply) == ["hedge"]


def test_compute_signals_shape():
    """Whatever is installed, the result is the training shape: three signals,
    fixed order, numeric confidences (a missing model is unknown/0.0, never null)."""
    out = fr.compute_signals("Could you send the report by Friday?")
    assert [s["model"] for s in out] == ["tone", "politeness", "circa"]
    assert all(set(s) == {"model", "label", "confidence"} for s in out)
    assert all(isinstance(s["confidence"], (int, float)) for s in out)
