"""Politeness adapter - wraps Src/source/model/politeness/.

The model returns {"score", "level", "warnings"}. Mapping each piece:

`label` <- the model's own `level`. It is already a three-way low/medium/high
split, and its cut points are the *training-set tertiles* stored in the
model's metadata, currently:

    score <  -0.2049            -> "low"
    -0.2049 <= score <  0.3116  -> "medium"
    score >=  0.3116            -> "high"

Those thresholds are read from metadata.json at load time, never hardcoded
here, so a retrain that shifts the distribution shifts the labels with it.
They are relative to the Stanford corpus, so "high" means polite *for a
Wikipedia or Stack Exchange request*, not polite in absolute terms.

`confidence` <- NOT the score. The score is a signed politeness rating,
roughly -3.7..+2.5 on the corpus and -1.45..+1.50 in practice, so feeding it
into a field the prompt reads as "how much should I trust this" would make
the most confidently rude readings look the least trustworthy. Instead this
is an honest reliability proxy: 1.0 normally, dropped when the model itself
raises a warning that its input was outside what it can judge.

`note` <- carries the raw score, its scale, and the domain caveat, so the LLM
still sees the number and knows how to read it.
"""
from __future__ import annotations

from typing import Any

from .._lazy import Lazy
from ..contract import unavailable, validate
from ._paths import WEIGHTS_DIR, add_model_dir

MODEL_NAME = "politeness"
_WEIGHTS = WEIGHTS_DIR / "politeness_nn_iteration1"

# Reliability when the model flags its input as unjudgeable. Not zero: a short
# message still carries some signal, it is just weaker evidence.
_SHORT_INPUT_CONFIDENCE = 0.3
_FULL_CONFIDENCE = 1.0

_DOMAIN_CAVEAT = (
    "trained on Wikipedia and Stack Exchange requests, not workplace email; "
    "test Pearson 0.47"
)

def _load_bundle() -> tuple[Any, dict]:
    add_model_dir("politeness")
    from politeness_nn import load_bundle  # noqa: E402

    return load_bundle(_WEIGHTS)


# 30MB of weights - loading it once per racing thread is what makes the
# difference on a 1GB box.
_bundle = Lazy(_load_bundle)


def _load() -> tuple[Any, dict]:
    """Load the NumPy model once. NumPy only - no torch, so this fits a t3.micro."""
    return _bundle.get()


def predict(text: str) -> dict[str, Any]:
    """Politeness comment on `text`, in the contract shape.

    Never raises: any failure degrades to the unavailable stub so one broken
    model cannot take down a request.
    """
    try:
        model, metadata = _load()
        add_model_dir("politeness")
        from politeness_nn import predict_message  # noqa: E402

        raw = predict_message(text, model, metadata)

        warnings = list(raw.get("warnings") or [])
        confidence = _SHORT_INPUT_CONFIDENCE if warnings else _FULL_CONFIDENCE

        low, high = metadata["target"]["tertile_thresholds"]
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
