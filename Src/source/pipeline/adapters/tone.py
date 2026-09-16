"""Tone adapter - wraps Src/source/model/tone/.

A thin pass-through: that model already returns the contract shape, so this
validates rather than reshapes. Two things it does add.

First, the import is lazy. enron_evaluate_and_predict imports torch at module
level, so importing it anywhere near module scope would make a missing torch
crash the whole pipeline at startup instead of degrading one signal.

Second, casual predictions get their confidence capped. The model's casual
recall is 0.30 on the held-out set - it misses roughly seven of every ten
casual messages, calling them neutral or terse. When it does say casual it
reports high softmax confidence anyway, because softmax measures the model's
internal certainty, not its accuracy on that class. Passing 0.97 through for
a class known to be wrong most of the time would tell the LLM to trust the
one label it should trust least.
"""
from __future__ import annotations

from typing import Any

from ..contract import unavailable, validate
from ._paths import add_model_dir

MODEL_NAME = "tone"

# Held-out per-class recall (300 hand-verified rows): neutral 0.87,
# terse 0.74, casual 0.30. Only casual is unreliable enough to cap.
_UNRELIABLE_CLASSES = {"casual"}
_UNRELIABLE_CAP = 0.3


def predict(text: str) -> dict[str, Any]:
    """Tone comment on `text`, in the contract shape.

    Never raises: a missing torch, missing weights, or any runtime error
    degrades to the unavailable stub.
    """
    try:
        add_model_dir("tone")
        from enron_evaluate_and_predict import predict as _tone_predict  # noqa: E402

        raw = dict(_tone_predict(text))
        raw["model"] = MODEL_NAME  # the model self-reports "tone"; pin it anyway

        label = str(raw.get("label", ""))
        if label in _UNRELIABLE_CLASSES:
            reported = float(raw.get("confidence", 0.0))
            raw["confidence"] = min(reported, _UNRELIABLE_CAP)
            note = str(raw.get("note", ""))
            raw["note"] = (
                f"{note}; confidence capped from {reported:.2f} to "
                f"{raw['confidence']:.2f} - '{label}' recall is 0.30 on the "
                f"held-out set, so this label is unreliable"
            ).lstrip("; ")

        return validate(raw)
    except Exception as exc:  # noqa: BLE001 - deliberate: never propagate
        return unavailable(MODEL_NAME, type(exc).__name__)
