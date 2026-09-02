"""Encapsulates message decoding for POST /api/decode.

Contract (see docs/api-contract.md): given raw message text, return the four
extracted elements (Time, Task-To-Do, Deadline, For whom) plus a category
classification bounded to the fixed enum used by the patterns table. Never
invent a value for an element the message doesn't state, return "Not
specified" instead.

This version is rule-based and span-grounded (see extraction.py) rather
than a model call, so the "never invent" rule holds by construction:
every returned value is a verbatim substring of the input. The hosted-vs-
self-hosted model decision stays open, and `category` stays null until a
classifier bounded to the category enum exists.
"""
import re
from typing import Optional

from .extraction import extract_all, is_meaningless

NOT_SPECIFIED = "Not specified"

# Engine field name -> API contract element key.
_FIELD_TO_ELEMENT = {
    "time": "time",
    "task_to_do": "task",
    "deadline": "deadline",
    "for_whom": "for_whom",
}

# Kept in step with frontend/src/services/localDecoder.ts so the API and
# the offline fallback prompt the user with the same wording.
PROMPTS = {
    "time": "What time do you need this by?",
    "task": "What exactly needs to be done?",
    "deadline": "When is this actually due?",
    "for_whom": "Who is this for?",
}


# Phrase -> category, kept in step with CATEGORY_TRIGGERS in
# frontend/src/services/localPatterns.ts (the offline fallback uses the
# same rules so it classifies identically to this endpoint). Order
# matters: the first match wins on both sides, so keep them aligned.
#
# This is deterministic phrase matching bounded to the category enum in
# docs/api-contract.md, not a guess - the "never invent meaning" rule
# constrains element values, which stay verbatim spans either way.
_CATEGORY_RULES = [
    (re.compile(r"when you get a chance", re.I), "Softened request"),
    (re.compile(r"\bbefore\b[^.,!?\n]*", re.I), "Vague deadline"),
    (re.compile(r"\b(loop in|whoever|if that'?s easier)\b", re.I), "Unassigned owner"),
    (re.compile(r"\bjust a few\b|\bsmall tweaks?\b", re.I), "Feedback framing"),
    (re.compile(r"no pressure", re.I), "Softened request"),
    (re.compile(r"\beod\b|end of day|\bthis week\b", re.I), "Vague deadline"),
    (
        re.compile(r"not let it slip|not urgent,? but|prioriti[sz]e|not sure how (?:much|important)", re.I),
        "Unclear priority",
    ),
    (re.compile(r"\bclean up\b|\btake a pass\b|\btighten up\b|\blook into\b", re.I), "Undefined scope"),
]


def classify(message: str) -> Optional[str]:
    """Category for the pattern-library join, or None if nothing matches.

    Bounded to the fixed enum - free text here would silently break the
    patterns join (see docs/api-contract.md). None is a valid answer and
    the frontend handles it: no category means no flashcard suggestion.
    """
    for pattern, category in _CATEGORY_RULES:
        if pattern.search(message):
            return category
    return None


def _tasks_payload(message: str, clauses, fields: dict) -> list:
    """One bullet per ask, each carrying only the fields inside its own clause.

    A field belongs to the task whose region contains it, where a region runs
    from that task's clause to the start of the next one. That is what makes
    the gaps per-bullet - "no deadline on the second item" - rather than one
    verdict for the whole message.
    """
    others = ("time", "deadline", "for_whom")
    payload = []

    for i, clause in enumerate(clauses):
        region_start = clause.span[0]
        region_end = clauses[i + 1].span[0] if i + 1 < len(clauses) else len(message)

        entry = {"text": clause.value, "span": clause.span}
        missing = []
        for key in others:
            result = fields[key]
            inside = (
                result.specified
                and result.span is not None
                and region_start <= result.span[0] < region_end
            )
            entry[key] = result.value if inside else NOT_SPECIFIED
            if not inside:
                missing.append({"field": key, "prompt": PROMPTS[key]})
        entry["missing"] = missing
        payload.append(entry)

    return payload


def decode(message: str) -> dict:
    """Decode `message` into the contract's response shape.

    Raises ValueError if the message is empty or meaningless; the route
    turns that into the contract's 400 response.
    """
    if is_meaningless(message):
        raise ValueError("Please enter a message")

    fields, clauses = extract_all(message)

    elements = {}
    spans = {}
    for field_name, result in fields.items():
        key = _FIELD_TO_ELEMENT[field_name]
        elements[key] = result.value if result.specified else NOT_SPECIFIED
        # Additive to the contract: character offsets into the original
        # message, so the UI can highlight where each value came from.
        spans[key] = result.span if result.specified else None

    covered = [key for key, value in elements.items() if value != NOT_SPECIFIED]
    missing = [
        {"field": key, "prompt": PROMPTS[key]}
        for key, value in elements.items()
        if value == NOT_SPECIFIED
    ]

    return {
        "elements": elements,
        "covered": covered,
        "missing": missing,
        "category": classify(message),
        "spans": spans,
        # Additive to the v1 contract: every ask in the message, with the
        # gaps scoped to each one. `elements` stays the single-task view.
        "tasks": _tasks_payload(message, clauses, fields),
    }
