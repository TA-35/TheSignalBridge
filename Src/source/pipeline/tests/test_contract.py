"""Contract validator tests."""
from __future__ import annotations

import math

import pytest

from Src.source.pipeline.contract import (
    ContractError,
    ModelComment,
    is_unavailable,
    unavailable,
    validate,
)

GOOD = {"model": "tone", "label": "neutral", "confidence": 0.91, "note": "n/a"}


def test_accepts_a_well_formed_output():
    assert validate(GOOD)["confidence"] == 0.91


def test_coerces_int_confidence_to_float():
    out = validate({**GOOD, "confidence": 1})
    assert isinstance(out["confidence"], float) and out["confidence"] == 1.0


@pytest.mark.parametrize("field", sorted(GOOD))
def test_rejects_a_missing_field(field):
    with pytest.raises(ContractError, match="missing required field"):
        validate({k: v for k, v in GOOD.items() if k != field})


def test_rejects_an_unexpected_field():
    with pytest.raises(ContractError, match="unexpected field"):
        validate({**GOOD, "spans": [[0, 4]]})


@pytest.mark.parametrize("value", [-0.01, 1.01, 42.0, -1.4])
def test_rejects_confidence_outside_zero_to_one(value):
    # -1.4 is the case that matters: a raw politeness score, which must never
    # reach this field.
    with pytest.raises(ContractError, match=r"within \[0, 1\]"):
        validate({**GOOD, "confidence": value})


def test_rejects_nan_confidence():
    with pytest.raises(ContractError, match="NaN"):
        validate({**GOOD, "confidence": math.nan})


def test_rejects_boolean_confidence():
    # bool subclasses int, so a naive isinstance check would let True through.
    with pytest.raises(ContractError, match="confidence"):
        validate({**GOOD, "confidence": True})


@pytest.mark.parametrize("field", ["model", "label"])
def test_rejects_empty_identifier(field):
    with pytest.raises(ContractError, match="must not be empty"):
        validate({**GOOD, field: "   "})


def test_rejects_wrong_type():
    with pytest.raises(ContractError, match="label: expected str"):
        validate({**GOOD, "label": 3})


def test_rejects_a_non_mapping():
    with pytest.raises(ContractError, match="expected a mapping"):
        validate(["model", "tone"])


def test_dataclass_validates_on_construction():
    assert ModelComment(**GOOD).as_dict() == GOOD
    with pytest.raises(ContractError):
        ModelComment(model="tone", label="neutral", confidence=9.0, note="")


def test_unavailable_stub_satisfies_the_contract():
    stub = unavailable("circa", "no saved weights")
    validate(stub)
    assert stub["confidence"] == 0.0
    assert is_unavailable(stub)
    assert "no saved weights" in stub["note"]


def test_real_output_is_not_flagged_unavailable():
    assert not is_unavailable(GOOD)
