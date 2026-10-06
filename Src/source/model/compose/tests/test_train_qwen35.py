"""Tests for the parts of train_qwen35.py that run before the GPU stack loads.

The template tests use a small fake of Qwen's ChatML template with thinking
off, so they check our logic, not Qwen's; the dry run on the GPU box checks
the real template.
"""
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("train_qwen35", HERE.parent / "train_qwen35.py")
tq = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tq)
cp = tq.cp

GOOD = {"id": "x1", "dataset": "enron", "source": "can u send the deck", "signals": [],
        "meaning": {}, "rewrite": "Could you send the deck?", "notes": ["Made the ask direct."]}


def _write(tmp_path, rows):
    path = tmp_path / "train.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


# --------------------------------------------------------------------------
# Data checks
# --------------------------------------------------------------------------

def test_load_keeps_only_the_fields_training_reads(tmp_path):
    rows = tq.load_records(_write(tmp_path, [GOOD]), set(), cp.fingerprint())
    assert rows == [{k: GOOD[k] for k in ("id", "source", "signals", "rewrite", "notes")}]


def test_load_refuses_a_gold_message(tmp_path):
    gold = {tq._norm("Can u  send the DECK")}
    with pytest.raises(SystemExit, match="gold"):
        tq.load_records(_write(tmp_path, [GOOD]), gold, cp.fingerprint())


def test_load_refuses_an_old_prompt(tmp_path):
    with pytest.raises(SystemExit, match="made with prompt old123"):
        tq.load_records(_write(tmp_path, [dict(GOOD, prompt_version="old123")]), set(), cp.fingerprint())


def test_load_names_a_missing_field(tmp_path):
    bad = {k: v for k, v in GOOD.items() if k != "notes"}
    with pytest.raises(SystemExit, match=r"train.jsonl:1 is missing \['notes'\]"):
        tq.load_records(_write(tmp_path, [bad]), set(), cp.fingerprint())


def test_gold_sources_reads_the_real_gold_files():
    gold = tq.gold_sources()
    assert all(isinstance(g, str) for g in gold)


def test_dry_run_records_are_the_style_guide_examples():
    rows = tq.dry_run_records()
    assert len(rows) == tq.DRY_RUN_EXAMPLES
    assert {r["source"] for r in rows} == {e["source"] for e in cp.examples()}


# --------------------------------------------------------------------------
# Signal dropout
# --------------------------------------------------------------------------

def _many(n=400):
    sig = [{"model": "tone", "label": "casual", "confidence": 0.9},
           {"model": "politeness", "label": "high", "confidence": 0.555},
           {"model": "circa", "label": "direct", "confidence": 0.6}]
    return [dict(GOOD, id=str(i), signals=sig) for i in range(n)]


def test_dropout_rate_and_shape():
    out, dropped = tq.drop_signals(_many(), 0.1, seed=1)
    total = 3 * len(out)
    assert 0.07 < dropped / total < 0.13
    failed = [s for r in out for s in r["signals"] if s["label"] == "unknown"]
    assert len(failed) == dropped
    assert all(s == cp.failed_signal(s["model"]) for s in failed)


def test_dropout_is_reproducible_and_zero_means_none():
    assert tq.drop_signals(_many(), 0.1, seed=7) == tq.drop_signals(_many(), 0.1, seed=7)
    assert tq.drop_signals(_many(), 0.0, seed=7)[1] == 0


# --------------------------------------------------------------------------
# Messages and the chat template
# --------------------------------------------------------------------------

def test_messages_are_the_serving_prompt_plus_the_answer():
    messages = tq.to_messages(GOOD)
    assert messages[:-1] == cp.build_messages(GOOD["source"], GOOD["signals"])
    assert messages[-1] == {"role": "assistant", "content": cp.assistant_response(GOOD)}


class FakeQwen:
    """ChatML, and with thinking off an empty think block opens the answer."""

    def __init__(self, think_in_history=True):
        self.think_in_history = think_in_history

    def apply_chat_template(self, messages, tokenize=False, enable_thinking=True,
                            add_generation_prompt=False):
        assert enable_thinking is False
        think = "<think>\n\n</think>\n\n"
        out = ""
        for m in messages:
            body = m["content"]
            if m["role"] == "assistant" and self.think_in_history:
                body = think + body
            out += f"<|im_start|>{m['role']}\n{body}<|im_end|>\n"
        if add_generation_prompt:
            out += "<|im_start|>assistant\n" + think
        return out


def test_response_marker_includes_the_empty_think_block():
    assert tq.response_marker(FakeQwen()) == "<|im_start|>assistant\n<think>\n\n</think>\n\n"


def test_train_matches_serve_passes_on_a_consistent_template():
    tq.check_train_matches_serving(FakeQwen(), tq.to_messages(GOOD))


def test_train_matches_serve_catches_a_template_that_drops_the_think_block():
    """If training text lacks the think block that serving adds, stop."""
    with pytest.raises(SystemExit, match="does not start with the serving prompt"):
        tq.check_train_matches_serving(FakeQwen(think_in_history=False), tq.to_messages(GOOD))
