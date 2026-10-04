"""Adapter tests, focused on the failure paths.

The contract exists so the pipeline survives a broken model, so what matters
most is that every adapter degrades instead of raising.

A note on the skips. Where weights may be absent, the guard checks for the
FILE, never for an unavailable result. Guarding on the result means a genuine
adapter failure makes the test excuse itself rather than fail - and it bit
once: a test skipped on is_unavailable() stopped skipping when the adapter was
fixed to fall back, and failed in CI while passing on any machine that had the
optional weights.
"""
from __future__ import annotations

import pytest

from Src.source.pipeline.adapters import circa, politeness, tone
from Src.source.pipeline.contract import is_unavailable, validate

ADAPTERS = [politeness, tone, circa]
ADAPTER_IDS = [m.MODEL_NAME for m in ADAPTERS]


@pytest.mark.parametrize("adapter", ADAPTERS, ids=ADAPTER_IDS)
def test_output_always_satisfies_the_contract(adapter):
    """Whether the model loads or not, the shape is the same."""
    validate(adapter.predict("Could you review the deck before Thursday?"))


@pytest.mark.parametrize("adapter", ADAPTERS, ids=ADAPTER_IDS)
@pytest.mark.parametrize("text", ["", "   ", "\n\n", "?", "x" * 20000])
def test_survives_degenerate_input(adapter, text):
    validate(adapter.predict(text))


@pytest.mark.parametrize("adapter", ADAPTERS, ids=ADAPTER_IDS)
def test_returns_stub_instead_of_raising_when_the_model_explodes(adapter, monkeypatch):
    """The failure path: a model that throws must not reach the caller."""
    def boom(*_args, **_kwargs):
        raise RuntimeError("weights corrupted")

    # Break each adapter at its own loading seam.
    if adapter is politeness:
        monkeypatch.setattr(politeness, "_load", boom)
    elif adapter is tone:
        monkeypatch.setattr(tone, "add_model_dir", boom)
    else:
        monkeypatch.setattr(circa, "_load", boom)

    out = adapter.predict("Can you take a look at this?")
    validate(out)
    assert is_unavailable(out)
    assert out["confidence"] == 0.0
    assert out["label"] == "unknown"
    assert out["model"] == adapter.MODEL_NAME


def test_tone_stubs_when_torch_is_missing(monkeypatch):
    """torch is imported lazily; without it the pipeline degrades, not dies."""
    import builtins

    real_import = builtins.__import__

    def no_torch(name, *args, **kwargs):
        if name.startswith("torch") or name == "enron_register":
            raise ImportError("No module named 'torch'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_torch)
    out = tone.predict("thanks!")
    assert is_unavailable(out)
    assert "ImportError" in out["note"]


def test_politeness_confidence_is_a_proxy_not_the_score():
    """The score is signed and unbounded; confidence must stay a 0-1 trust value."""
    if not (politeness._WEIGHTS / "politeness_mlp.npz").exists():
        pytest.skip("politeness weights not present")
    out = politeness.predict(
        "Would you mind taking a look at the deck when you have a moment? Thank you."
    )
    assert not is_unavailable(out), "weights are present, so this must not stub"
    assert 0.0 <= out["confidence"] <= 1.0
    assert out["label"] in {"low", "medium", "high"}
    # The raw score is preserved for the LLM, just not in `confidence`.
    assert "politeness score" in out["note"]


def test_politeness_lowers_confidence_on_short_input():
    if not (politeness._WEIGHTS / "politeness_mlp.npz").exists():
        pytest.skip("politeness weights not present")
    short = politeness.predict("do it")
    assert not is_unavailable(short), "weights are present, so this must not stub"
    assert short["confidence"] == politeness._SHORT_INPUT_CONFIDENCE
    assert "confidence lowered" in short["note"]


def _stub_tone(monkeypatch, label, confidence):
    """Fake enron_register so the tests don't need the real weights."""
    import sys, types

    monkeypatch.setattr(tone, "add_model_dir", lambda _name: None)
    scores = {"neutral": 0.0, "casual": 0.0, "formal": 0.0}
    scores[label] = confidence
    stub = types.ModuleType("enron_register")
    stub.MODEL_DIR = None
    stub.classify = lambda body: {"tone": label, "tone_scores": scores}
    monkeypatch.setitem(sys.modules, "enron_register", stub)


def test_tone_caps_confidence_on_the_unreliable_class(monkeypatch):
    """formal precision is 0.58, so a confident 'formal' must not stay confident."""
    _stub_tone(monkeypatch, "formal", 0.97)

    out = tone.predict("Dear Mr Smith, I would appreciate your confirmation.")
    validate(out)
    assert out["label"] == "formal"
    assert out["confidence"] == tone._UNRELIABLE_CAP
    assert "precision is 0.58" in out["note"]


@pytest.mark.parametrize("label", ["neutral", "casual"])
def test_tone_passes_reliable_classes_through_untouched(monkeypatch, label):
    """casual is reliable now (recall 0.85), so only formal gets capped."""
    _stub_tone(monkeypatch, label, 0.93)

    out = tone.predict("Please send the report by Friday.")
    validate(out)
    assert out["label"] == label
    assert out["confidence"] == 0.93
    assert out["note"] == f"register reads as {label}"


# --------------------------------------------------------------------------
# Circa variant selection
# --------------------------------------------------------------------------

def test_circa_uses_answer_only_when_no_question_is_available():
    """The default path: our flows have no question, and answer-only is the
    better model on that input (0.610 vs v2's 0.590 with a blank question)."""
    if not circa._bundle_file("answer_only").exists():
        pytest.skip("circa weights not present")
    out = circa.predict("Yeah, I might be around later if things wrap up early.")
    assert not is_unavailable(out), "weights are present, so this must not stub"
    assert "circa_nn.py" in out["note"]
    assert "answer_only" in out["note"]


def test_circa_switches_to_v2_when_a_question_is_supplied():
    """v2 activates on its own the day a flow starts collecting a question.

    Skipped where the v2 weights are absent, which is every fresh checkout and
    CI - they are gitignored at 64MB for a variant no user flow reaches.

    The precondition is the weights file, not an unavailable result. An earlier
    version guarded on is_unavailable(), which held only while a missing v2
    produced the stub; once the adapter was fixed to fall back to answer_only,
    that guard stopped firing and the test failed in CI while passing on any
    machine that happened to have the weights."""
    if not circa._bundle_file("question_answer").exists():
        pytest.skip("circa v2 weights not present (gitignored)")
    out = circa.predict(
        "Yeah, I might be around later if things wrap up early.",
        question="Are you coming to drinks on Friday?",
    )
    validate(out)
    assert "circa_nn_v2.py" in out["note"]
    assert "0.647" in out["note"]


@pytest.mark.parametrize("question", [None, "", "   "])
def test_a_blank_question_does_not_trigger_v2(question):
    """Serving v2 a blank question measures 0.590 - worse than not using it."""
    if not circa._bundle_file("answer_only").exists():
        pytest.skip("circa weights not present")
    out = circa.predict("Sure, sounds good.", question=question)
    assert not is_unavailable(out), "weights are present, so this must not stub"
    assert "answer_only" in out["note"]


def test_circa_still_stubs_when_the_chosen_variant_has_no_weights(monkeypatch, tmp_path):
    monkeypatch.setitem(circa.VARIANTS, "answer_only",
                        {**circa.VARIANTS["answer_only"], "dir": tmp_path / "gone"})
    out = circa.predict("Sure, sounds good.")
    assert is_unavailable(out)
    assert "no saved weights" in out["note"]


def test_a_question_without_v2_weights_falls_back_rather_than_stubbing(monkeypatch, tmp_path):
    """v2 is gitignored, so it is absent from every fresh checkout and from
    the inference host. Selecting it there loses the circa signal entirely -
    a caller supplying a question would get less than one that does not.

    This pins the weights check in _choose_variant: it was removed once as a
    redundant-looking condition, which turned a working fallback into
    'model unavailable' wherever the optional weights are not present.
    """
    monkeypatch.setitem(circa.VARIANTS, "question_answer",
                        {**circa.VARIANTS["question_answer"], "dir": tmp_path / "absent"})
    out = circa.predict("Yeah, maybe later.", question="Coming Friday?")
    if is_unavailable(out) and "answer_only" not in out["note"]:
        assert out["note"].startswith("model unavailable") is False, (
            "a missing optional variant must fall back, not stub out")
    assert not is_unavailable(out), "should have fallen back to answer_only"
    assert "answer_only" in out["note"]
