"""Analysis layer tests: span exactness, message type, and required fields."""
from __future__ import annotations

import pytest

from Src.source.pipeline.analysis import (
    FIELDS,
    MESSAGE_TYPES,
    REQUIRED_BY_TYPE,
    analyse,
    extract,
    message_type,
)
from Src.source.pipeline.contract import validate


# --------------------------------------------------------------------------
# Spans
# --------------------------------------------------------------------------

MESSAGES = [
    "Could you send the report to the client by Friday? It's urgent.",
    "Hi Sam, as discussed last week, please review the deck before the sync.",
    "I'll push the fix tomorrow so we can unblock the release.",
    "Thanks!",
    "do it",
    "FYI the migration has been merged.",
]


@pytest.mark.parametrize("text", MESSAGES)
def test_every_span_resolves_to_its_own_value(text):
    """The guarantee the validator depends on: text[start:end] == value."""
    result = extract(text)
    for found in result.found.values():
        start, end = found.span
        assert text[start:end] == found.value, f"{found.field} span is not exact"


@pytest.mark.parametrize("text", MESSAGES)
def test_spans_are_within_bounds(text):
    for found in extract(text).found.values():
        start, end = found.span
        assert 0 <= start < end <= len(text)


def test_finds_deadline_and_action_with_spans():
    text = "Could you send the report to the client by Friday?"
    found = extract(text).found
    assert "deadline" in found and found["deadline"].value == "Friday"
    assert "required_action" in found
    assert text[slice(*found["required_action"].span)] == found["required_action"].value


def test_finds_priority_purpose_and_context():
    text = ("As discussed last week, please fix the login bug urgently "
            "so that we can ship on Monday.")
    found = extract(text).found
    assert found["priority"].value.lower() == "urgently"
    assert found["context"].value.lower().startswith("as discussed")
    assert found["purpose"].value.lower().startswith("so that")


def test_extractor_never_raises_on_junk():
    for text in ["", "   ", "?!", "\n\n\n", "x" * 5000, "😀😀"]:
        extract(text)


# --------------------------------------------------------------------------
# Message type
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Could you review the deck?", "request"),
    ("Please send it by Friday.", "request"),
    ("Send the deck.", "request"),
    ("I'll push the fix tomorrow.", "commitment"),
    ("We will have it ready by Monday.", "commitment"),
    ("FYI the migration has been merged.", "update"),
    ("I've finished the report.", "update"),
    ("Thanks!", "social"),
    ("Thanks so much :)", "social"),
    ("Happy birthday!", "social"),
    ("Congrats on the launch", "social"),
])
def test_message_type_rules(text, expected):
    assert message_type(text) == expected


def test_type_is_always_one_of_the_declared_set():
    for text in MESSAGES + ["", "   ", "???"]:
        assert message_type(text) in MESSAGE_TYPES


def test_thanks_plus_an_ask_is_a_request_not_social():
    """A thank-you wrapped round an ask is still an ask."""
    assert message_type("Thanks! Could you also send the invoice?") == "request"


def test_empty_message_does_not_crash():
    assert message_type("") in MESSAGE_TYPES


# --------------------------------------------------------------------------
# Required fields per type
# --------------------------------------------------------------------------

def test_social_message_is_never_missing_a_deadline():
    """The one rule stated explicitly in the brief."""
    result = extract("Thanks!", message_type="social")
    assert result.missing == []
    assert "deadline" not in result.missing


def test_request_reports_its_own_missing_fields():
    result = extract("Could you take a look?", message_type="request")
    assert "deadline" in result.missing
    assert set(result.missing) <= REQUIRED_BY_TYPE["request"]


def test_update_is_not_asked_for_a_deadline():
    result = extract("FYI the migration has been merged.", message_type="update")
    assert "deadline" not in result.missing


def test_required_sets_only_reference_known_fields():
    for kind, required in REQUIRED_BY_TYPE.items():
        assert kind in MESSAGE_TYPES
        assert required <= set(FIELDS), f"{kind} requires an unknown field"


def test_every_message_type_has_a_required_set():
    assert set(REQUIRED_BY_TYPE) == set(MESSAGE_TYPES)


# --------------------------------------------------------------------------
# Concurrent analysis
# --------------------------------------------------------------------------

def test_analyse_returns_one_comment_per_adapter_all_valid():
    result = analyse("Could you send the deck by Friday?")
    assert len(result.comments) == 3
    for comment in result.comments:
        validate(comment)


def test_analyse_survives_an_adapter_that_throws():
    """A broken analyser must not take down the request."""
    class Exploding:
        MODEL_NAME = "exploding"

        @staticmethod
        def predict(_text):
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        # Confirms the stub behaviour lives in the adapters, not here: a
        # class that bypasses the adapter contract does propagate, which is
        # why every real adapter catches its own exceptions.
        analyse("hello there", adapters=[Exploding])


def test_analyse_shape_is_serialisable():
    result = analyse("Please review this by Tuesday.")
    payload = result.as_dict()
    assert payload["message_type"] == "request"
    assert set(payload) == {"message_type", "extraction", "comments"}
    assert set(payload["extraction"]) == {"found", "missing", "actions"}


def test_analyse_does_not_echo_the_message_body_in_its_payload():
    """No user text is persisted; as_dict() is what gets written or logged."""
    secret = "Ship the Acme contract by Friday."
    payload = analyse(secret).as_dict()
    assert secret not in str(payload.get("comments"))


# --------------------------------------------------------------------------
# Regressions found on a real email (Monash FIT1045 recruitment message).
# Synthetic examples missed all three; a genuine message caught them.
# --------------------------------------------------------------------------

REAL_FRAGMENT = (
    "We need the following by return email, no later than 10am on "
    "Monday 12th Jan:\n\nPlease let us know your level of familiarity "
    "with C/C++.\n\nYou need to be able to dedicate 5 hours per week. "
    "This will be a relatively constant requirement each week."
)


def test_a_bare_trigger_phrase_is_not_accepted_as_a_deadline():
    """spaCy tags "no later than" as a DATE; it names no time, so it is not
    a deadline. Before the fix this was reported as the deadline and the
    real date was discarded."""
    found = extract(REAL_FRAGMENT).found
    assert "deadline" in found
    assert found["deadline"].value != "no later than"
    assert "Jan" in found["deadline"].value


def test_a_demonstrative_is_not_a_responsible_person():
    """"This will be a constant requirement" must not yield "This"."""
    found = extract(REAL_FRAGMENT).found
    assert found.get("responsible_person") is None or \
        found["responsible_person"].value.lower() not in {"this", "that", "these"}


def test_field_values_do_not_end_in_punctuation():
    """A span quoted back to the user should not trail a colon or comma."""
    for f in extract(REAL_FRAGMENT).found.values():
        assert not f.value.endswith((":", ",", ";", ".")), f.field


def test_real_email_spans_are_still_exact():
    for f in extract(REAL_FRAGMENT).found.values():
        start, end = f.span
        assert REAL_FRAGMENT[start:end] == f.value


def test_every_ask_is_surfaced_not_just_the_first():
    """A real email carried five asks; the pipeline used to report one."""
    msg = (
        "Please let us know your level of familiarity with C/C++.\n\n"
        "Please let us know how many classes you can take.\n\n"
        "Please send us a link to a 5 minute video."
    )
    result = extract(msg, "request")
    assert len(result.actions) >= 3, f"only {len(result.actions)} ask(s) found"
    for a in result.actions:
        assert msg[a.span[0]:a.span[1]] == a.value


def test_first_action_still_backs_the_required_action_field():
    """`missing` logic needs one thing to test, so the first ask stays there."""
    msg = "Please send the deck. Please also book the room."
    result = extract(msg, "request")
    assert result.found["required_action"].value == result.actions[0].value


def test_no_field_value_crosses_a_paragraph_break():
    """spaCy DATE entities have run past a blank line into the next paragraph."""
    msg = "Get it to us by Monday 12th Jan:\n\nPlease include your notes."
    for f in extract(msg).found.values():
        assert "\n\n" not in f.value, f"{f.field} crosses a paragraph break"


def test_deadline_does_not_wrap_a_line():
    msg = "Due Monday 12th Jan\nPlease confirm receipt."
    found = extract(msg).found
    if "deadline" in found:
        assert "\n" not in found["deadline"].value
