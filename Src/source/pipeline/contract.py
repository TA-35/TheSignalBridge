"""The output contract every model adapter must satisfy.

One shape for all three models, so prompt.py can lay them out uniformly and
the LLM can weigh them against each other without special-casing per model.

    {"model": str, "label": str, "confidence": float, "note": str}

`confidence` means one thing everywhere: how much this signal should be
trusted, 0.0 (ignore) to 1.0 (fully trusted). That uniformity is the whole
point of the field - the prompt tells the LLM to discount low-confidence
comments, so a number that means "probability" for one model and something
else for another would silently mislead it. Adapters whose model does not
emit a probability derive an honest proxy and explain it in `note`.

`note` is free text shown to the LLM, not to the user. It is where a model
puts anything the contract cannot hold: a raw score, a known weakness, the
reason confidence was lowered.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


class ContractError(ValueError):
    """A model output that does not satisfy the contract."""


@dataclass(frozen=True)
class ModelComment:
    """One model's comment on a message."""

    model: str
    label: str
    confidence: float
    note: str = ""

    def __post_init__(self) -> None:
        validate(asdict(self))

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


REQUIRED_FIELDS: dict[str, type | tuple[type, ...]] = {
    "model": str,
    "label": str,
    "confidence": (int, float),
    "note": str,
}


def validate(output: Mapping[str, Any]) -> dict[str, Any]:
    """Raise ContractError unless `output` satisfies the contract.

    Returns the output as a plain dict so callers can use it directly.
    """
    if not isinstance(output, Mapping):
        raise ContractError(f"expected a mapping, got {type(output).__name__}")

    missing = [f for f in REQUIRED_FIELDS if f not in output]
    if missing:
        raise ContractError(f"missing required field(s): {sorted(missing)}")

    extra = [k for k in output if k not in REQUIRED_FIELDS]
    if extra:
        raise ContractError(f"unexpected field(s): {sorted(extra)}")

    for field, expected in REQUIRED_FIELDS.items():
        value = output[field]
        # bool is a subclass of int; a boolean confidence is a bug, not a value.
        if isinstance(value, bool) or not isinstance(value, expected):
            name = getattr(expected, "__name__", "float")
            raise ContractError(
                f"{field}: expected {name}, got {type(value).__name__}"
            )

    if not output["model"].strip():
        raise ContractError("model: must not be empty")
    if not output["label"].strip():
        raise ContractError("label: must not be empty")

    confidence = float(output["confidence"])
    if confidence != confidence:  # NaN
        raise ContractError("confidence: must not be NaN")
    if not 0.0 <= confidence <= 1.0:
        raise ContractError(f"confidence: must be within [0, 1], got {confidence}")

    return {**output, "confidence": confidence}


UNAVAILABLE_NOTE = "model unavailable"


def unavailable(model: str, reason: str = "") -> dict[str, Any]:
    """The stub every adapter returns instead of raising.

    One broken model must not take down a request, so an adapter that cannot
    load its weights, or that throws, degrades to this. confidence 0.0 tells
    the prompt to ignore it entirely.
    """
    note = UNAVAILABLE_NOTE if not reason else f"{UNAVAILABLE_NOTE}: {reason}"
    return {
        "model": model,
        "label": "unknown",
        "confidence": 0.0,
        "note": note,
    }


def is_unavailable(output: Mapping[str, Any]) -> bool:
    """True if `output` is an unavailable stub rather than a real prediction."""
    return str(output.get("note", "")).startswith(UNAVAILABLE_NOTE)
