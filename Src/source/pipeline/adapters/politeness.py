"""Politeness adapter - wraps Src/source/model/politeness/politeness_v2.py.

Iteration 2 model: a NumPy-only text CNN distilled from a fine-tuned RoBERTa
teacher (docs/models/STANFORD_POLITENESS_NN_ITERATION2.md). It returns
{"score", "level", "warnings"}. Mapping each piece:

`label` <- the model's own `level`. Its cut points are the tertiles of the
model's *validation predictions*, stored in metadata as
levels.prediction_cutoffs, currently:

    score <  -0.0968            -> "low"
    -0.0968 <= score <  0.2041  -> "medium"
    score >=  0.2041            -> "high"

They are read from metadata.json at load time, never hardcoded here, so a
retrain moves the labels with it. They are relative to the Stanford corpus,
so "high" means polite *for a Wikipedia or Stack Exchange request*, not
polite in absolute terms.

`confidence` <- NOT the score. The score is a signed politeness rating, so
feeding it into a field the prompt reads as "how much should I trust this"
would make the most confidently rude readings look the least trustworthy.
Instead it is the model's held-out 3-class accuracy (metrics.test.acc3 in
metadata, 0.555), the honest answer to "how often is this label right".
Iteration 1 reported a flat 1.0 here, which told the LLM to trust a model
that was right less than half the time. It drops further when the model
warns that its input was outside what it can judge.

`note` <- carries the raw score, its scale, and the domain caveat, so the LLM
still sees the number and knows how to read it.
"""
from __future__ import annotations

from typing import Any

from .._lazy import Lazy
from ..contract import unavailable, validate
from ._paths import WEIGHTS_DIR, add_model_dir

MODEL_NAME = "politeness"
_WEIGHTS = WEIGHTS_DIR / "politeness_nn_iteration2"

# Reliability when the model flags its input as unjudgeable. Not zero: a short
# message still carries some signal, it is just weaker evidence.
_SHORT_INPUT_CONFIDENCE = 0.3

_DOMAIN_CAVEAT = (
    "trained on Wikipedia and Stack Exchange requests, not workplace email; "
    "test Pearson 0.56"
)

def _load_bundle() -> tuple[Any, dict, dict]:
    add_model_dir("politeness")
    from politeness_v2 import load_bundle  # noqa: E402

    return load_bundle(_WEIGHTS)


# Load once even when requests race on a cold start; it matters on a 1GB box.
_bundle = Lazy(_load_bundle)


def _load() -> tuple[Any, dict, dict]:
    """Load the NumPy model once. NumPy only - no torch, so this fits a t3.micro."""
    return _bundle.get()


def predict(text: str) -> dict[str, Any]:
    """Politeness comment on `text`, in the contract shape.

    Never raises: any failure degrades to the unavailable stub so one broken
    model cannot take down a request.
    """
    try:
        model, vocab, metadata = _load()
        add_model_dir("politeness")
        from politeness_v2 import predict_message  # noqa: E402

        raw = predict_message(text, model, vocab, metadata)

        warnings = list(raw.get("warnings") or [])
        full = float(metadata["metrics"]["test"]["acc3"])
        confidence = min(_SHORT_INPUT_CONFIDENCE, full) if warnings else full

        low, high = metadata["levels"]["prediction_cutoffs"]
        note = (
            f"politeness score {raw['score']:+.3f} "
            f"(negative is blunt, positive is polite; "
            f"low/medium/high cut at {low:+.3f} and {high:+.3f}); "
            f"{_DOMAIN_CAVEAT}"
        )
        if warnings:
            note += f"; confidence lowered - model warned: {', '.join(warnings)}"

        return validate({
            "model": MODEL_NAME,
            "label": str(raw["level"]),
            "confidence": confidence,
            "note": note,
        })
    except Exception as exc:  # noqa: BLE001 - deliberate: never propagate
        return unavailable(MODEL_NAME, type(exc).__name__)
