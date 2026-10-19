"""Runs the four analysers over a message and collects their output.

Three model adapters plus a spaCy extractor, concurrently. Threads, not
processes: spaCy and scikit-learn release the GIL inside their native code,
and the whole point is that a slow model does not serialise behind the others.

Every span produced here is verified against the source text before it leaves
this module - `text[start:end] == value`, no exceptions. Downstream, the
validator trusts extractor spans as ground truth when it has to build
degraded output, so an unverified span here would poison that fallback.
"""
from __future__ import annotations

import importlib.util
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from ._lazy import Lazy
from .adapters import circa, politeness, tone
from .adapters._paths import REPO_ROOT

# --------------------------------------------------------------------------
# The fields we look for. One list, so changing it is a one-line edit.
# --------------------------------------------------------------------------

FIELDS: tuple[str, ...] = (
    "purpose",
    "required_action",
    "responsible_person",
    "deadline",
    "priority",
    "context",
)

MESSAGE_TYPES: tuple[str, ...] = ("request", "update", "commitment", "social")

# Which fields are worth flagging as missing, per message type.
#
# A field absent from a type's set is simply not that type's business: a
# social message has no deadline to omit, and flagging one would train the
# user to ignore the tool. These are a starting position, not a finding -
# they encode an assumption about what each kind of message owes its reader,
# and they are meant to be argued with.
REQUIRED_BY_TYPE: dict[str, frozenset[str]] = {
    # An ask is incomplete without what, who, and by when.
    "request": frozenset({"purpose", "required_action", "responsible_person", "deadline"}),
    # A promise owes the reader what is being promised and by when.
    "commitment": frozenset({"required_action", "deadline"}),
    # A status note owes the reader what changed and why it matters.
    "update": frozenset({"purpose", "context"}),
    # Nothing. Pleasantries are complete as they are.
    "social": frozenset(),
}


# --------------------------------------------------------------------------
# Reused extractor
# --------------------------------------------------------------------------

# backend/app/services/extraction.py already solves span-exact extraction of
# the action clause and the deadline, with trailing-noise trimming and a
# guarantee that text[start:end] == value. Rewriting that here would make a
# second implementation to keep in step, and this repository already has
# enough of those. It is loaded by file path rather than imported as
# backend.app.services.extraction because backend/app/__init__.py boots Flask
# and raises without SECRET_KEY - the module itself has no relative imports,
# so loading it directly is clean.
_BACKEND_EXTRACTOR = REPO_ROOT / "backend" / "app" / "services" / "extraction.py"

def _load_backend_extractor() -> Any:
    spec = importlib.util.spec_from_file_location(
        "_pipeline_backend_extraction", _BACKEND_EXTRACTOR
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {_BACKEND_EXTRACTOR}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Loaded once even when several analyser threads ask at the same moment.
_extraction = Lazy(_load_backend_extractor)


def _backend_extractor() -> Any:
    return _extraction.get()


# --------------------------------------------------------------------------
# Native patterns for the fields the backend extractor does not cover
# --------------------------------------------------------------------------

# Deliberately not reusing `for_whom` from the backend extractor: that field
# means the beneficiary ("a summary for the client"), which is a different
# question from who has to act. Conflating them would put the wrong name in
# front of the user.
_RESPONSIBLE_RE = re.compile(
    r"@([A-Za-z][\w.-]*)"
    r"|\b(?:can|could|would|will)\s+(you|[A-Z][a-z]+)\b"
    r"|\b([A-Z][a-z]+)\s+(?:will|should|needs to|is going to)\b"
    r"|\b(you)\s+(?:need to|should|must|have to)\b",
)

# Capitalised words that open a sentence and are not people. Without this,
# "This will be a constant requirement" yields "This" as the responsible
# person - caught on a real email, where it was one of three wrong fields.
_NOT_A_PERSON = frozenset({
    "this", "that", "these", "those", "there", "it", "we", "they", "he",
    "she", "you", "i", "the", "a", "an", "please", "thanks", "thank",
    "student", "students", "applied", "portfolio", "portfolios", "class",
    "classes", "details", "language", "summary", "confirmation", "video",
    "number", "regards", "hi", "hello", "so", "if", "and", "but", "our",
    "your", "their", "his", "her", "its", "all", "each", "every", "some",
})

# A deadline has to contain something time-shaped. spaCy tags bare trigger
# phrases as DATE entities - "no later than" comes back as a DATE - and the
# backend rule then promotes that to the deadline because "by" (from "by
# return email") sits in its trigger window, demoting the real date to
# `time`. Found on a real email: deadline read "no later than" while the
# actual "Monday 12th Jan" was discarded.
_TIME_SHAPED_RE = re.compile(
    r"\d"
    # Every day, whole or short. The old (?:day|s|nes|rs)? took one suffix, so
    # "Tuesday" (tue+s+day), "Wednesday", "Thursday" and "Saturday" never
    # matched and a deadline like "next Tuesday" was thrown away.
    r"|\b(?:mon|tues?|wed(?:nes|s)?|thu(?:rs?)?|fri|sat(?:ur)?|sun)(?:day)?s?\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\b"
    r"|\b(?:today|tomorrow|tonight|yesterday|noon|midnight|morning|"
    r"afternoon|evening|week|weeks|month|months|day|days|hour|hours|"
    r"eod|cob|asap|quarter|semester|term|deadline|now)\b",
    re.IGNORECASE,
)


def _is_time_shaped(value: str) -> bool:
    """True if `value` could plausibly name a point or span of time."""
    return bool(_TIME_SHAPED_RE.search(value))

_PURPOSE_RE = re.compile(
    r"\b(?:so that|so we can|so you can|in order to|because|to make sure|"
    r"the reason|this is for)\b[^.!?\n]*",
    re.IGNORECASE,
)

_PRIORITY_RE = re.compile(
    r"\b(?:urgent(?:ly)?|asap|as soon as possible|critical|blocker|blocking|"
    r"top priority|high priority|low priority|highest priority|"
    r"not urgent|no rush|whenever you (?:can|get)|when you get a chance|"
    r"time[- ]sensitive|priority)\b",
    re.IGNORECASE,
)

_CONTEXT_RE = re.compile(
    r"\b(?:as discussed|as we discussed|following up|follow(?:ing)? on|"
    r"per (?:our|the)|further to|circling back|as mentioned|"
    r"in (?:the|our|yesterday'?s|last week'?s) (?:meeting|call|standup|thread|email)|"
    r"last (?:week|month|time)|yesterday|earlier today)\b[^.!?\n]*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Found:
    """One field located in the message, with a verified character span."""

    field: str
    value: str
    span: tuple[int, int]

    def as_dict(self) -> dict[str, Any]:
        return {"field": self.field, "value": self.value, "span": list(self.span)}


@dataclass
class Extraction:
    """What the extractor found, and what it did not.

    `actions` holds *every* ask in the message, not just the first. A real
    workplace email routinely carries several - a recruitment message we
    tested against had five, and reporting only one made the tool look like
    it had read the first paragraph and stopped. `found["required_action"]`
    stays as the first ask so the missing-field logic has a single thing to
    test, but `actions` is what should be shown.
    """

    found: dict[str, Found] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    actions: list[Found] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "found": {k: v.as_dict() for k, v in self.found.items()},
            "missing": list(self.missing),
            "actions": [a.as_dict() for a in self.actions],
        }


# Trailing punctuation is never part of a field's value. spaCy entity spans
# include it ("Monday 12th Jan:" from a list header), and a span ending in a
# colon reads as sloppy when quoted back to the user.
_TRAILING_PUNCT = " \t\n:;,.!?-"


def _record(out: dict[str, Found], text: str, name: str, start: int, end: int) -> None:
    """Add a field, but only if its span is genuinely exact."""
    if name in out or start is None or end is None or start >= end:
        return
    value = text[start:end]

    # No field spans a paragraph break. spaCy entity spans sometimes run past
    # one - on a real email its DATE entity swallowed
    # "Monday 12th Jan:\n\nPlease", dragging the next paragraph's first word
    # into the deadline.
    if "\n\n" in value:
        value = value.split("\n\n", 1)[0]
    # A deadline additionally never wraps a single line; it is a date or a
    # time, not a clause.
    if name == "deadline" and "\n" in value:
        value = value.split("\n", 1)[0]

    value = value.strip().rstrip(_TRAILING_PUNCT)
    if not value:
        return
    # Re-derive the span from the stripped value so text[start:end] == value
    # holds even when the pattern caught surrounding whitespace.
    offset = text.index(value, start, end + len(value))
    span = (offset, offset + len(value))
    if text[span[0]:span[1]] != value:  # pragma: no cover - defensive
        return
    out[name] = Found(field=name, value=value, span=span)


def _first_match(out: dict[str, Found], text: str, name: str, pattern: re.Pattern) -> None:
    match = pattern.search(text)
    if match:
        _record(out, text, name, match.start(), match.end())


def extract(text: str, message_type: str | None = None) -> Extraction:
    """Locate each field in `text`, with spans. Never raises.

    `missing` is scoped to the message type: only fields that type actually
    owes its reader are reported, so a social message is never told it is
    missing a deadline.
    """
    found: dict[str, Found] = {}
    actions: list[Found] = []

    try:
        module = _backend_extractor()
        fields, clauses = module.extract_all(text)

        # Every ask, in document order. The backend extractor already
        # computes these; the pipeline used to keep clauses[0] and discard
        # the rest, which lost four of the five asks in a real email.
        seen: dict[str, Found] = {}
        for clause in clauses:
            if not (clause.specified and clause.span):
                continue
            _record(seen, text, f"action_{len(actions)}", clause.span[0], clause.span[1])
            latest = seen.get(f"action_{len(actions)}")
            if latest is not None:
                actions.append(Found(field="required_action",
                                     value=latest.value, span=latest.span))

        if actions:
            first = actions[0]
            found["required_action"] = first

        # Take the deadline only if it actually names a time. A bare trigger
        # phrase ("no later than") is spaCy mis-tagging, not a deadline.
        deadline = fields.get("deadline")
        if (
            deadline is not None
            and deadline.specified
            and deadline.span
            and _is_time_shaped(deadline.value or "")
        ):
            _record(found, text, "deadline", deadline.span[0], deadline.span[1])

        # `time` is the weaker signal - no trigger word attached - so it is
        # only used when the deadline slot is still empty, which now includes
        # the case where the deadline was rejected as not time-shaped.
        time_result = fields.get("time")
        if (
            "deadline" not in found
            and time_result is not None
            and time_result.specified
            and _is_time_shaped(time_result.value or "")
        ):
            _record(found, text, "deadline", time_result.span[0], time_result.span[1])
    except Exception:  # noqa: BLE001 - extraction is best-effort, never fatal
        pass

    _first_match(found, text, "purpose", _PURPOSE_RE)
    _first_match(found, text, "priority", _PRIORITY_RE)
    _first_match(found, text, "context", _CONTEXT_RE)

    for match in _RESPONSIBLE_RE.finditer(text):
        group = next((i for i in range(1, 5) if match.group(i)), None)
        if group is None:
            continue
        candidate = match.group(group)
        if candidate.lower() in _NOT_A_PERSON:
            continue  # "This will be...", not a person
        _record(found, text, "responsible_person", *match.span(group))
        break

    relevant = REQUIRED_BY_TYPE.get(message_type, frozenset(FIELDS)) if message_type else frozenset(FIELDS)
    missing = [f for f in FIELDS if f not in found and f in relevant]
    return Extraction(found=found, missing=missing, actions=actions)


# --------------------------------------------------------------------------
# Message type - rules only, no training
# --------------------------------------------------------------------------

_SOCIAL_ONLY_RE = re.compile(
    r"^\W*(?:thanks?(?:\s+(?:a lot|so much|again))?|thank you|ta|cheers|"
    r"congrats?(?:ulations)?|well done|nice work|good luck|happy birthday|"
    r"welcome(?:\s+aboard)?|hi|hello|hey|morning|good morning|good afternoon|"
    r"have a (?:good|great) (?:weekend|day|one)|see you|no worries|sounds good|"
    r"np|sure|ok(?:ay)?|great|awesome|perfect|\W|\s)+$",
    re.IGNORECASE,
)

# A social message that carries a little cargo: "Congrats on the launch",
# "Thanks for the quick turnaround". _SOCIAL_ONLY_RE cannot match these
# because of the tail, and spaCy reads the bare opener as an imperative noun
# ("Congrats" parses the same shape as "Send"), so without this they land as
# requests. The backend extractor's own greeting list covers thanks/hi/hello
# but not congratulations, and that list belongs to the live decode endpoint -
# safer to widen the net here than to change what the API already returns.
_SOCIAL_LEAD_RE = re.compile(
    r"^\W*(?:thanks?|thank you|ta|cheers|congrats?(?:ulations)?|well done|"
    r"nice (?:work|one|job)|good luck|happy \w+|welcome|hi|hello|hey|"
    r"good (?:morning|afternoon|evening)|morning|great (?:work|news))\b",
    re.IGNORECASE,
)

# Above this, a message that merely opens politely is doing something else as
# well, and the opener is a preamble rather than the point.
_SOCIAL_MAX_WORDS = 12

_REQUEST_RE = re.compile(
    r"\b(?:please|can you|could you|would you|will you|are you able to|"
    r"do you mind|would you mind|need you to|i need you|kindly|make sure you|"
    r"don'?t forget|let me know|send me|could we|can we)\b",
    re.IGNORECASE,
)

_COMMITMENT_RE = re.compile(
    r"\b(?:i(?:'| wi)ll|i will|i'm going to|i am going to|we(?:'| wi)ll|we will|"
    r"we're going to|i can (?:do|get|have|send)|i'?ve got it|on it|"
    r"i'?ll take|leave it with me|i shall)\b",
    re.IGNORECASE,
)

_UPDATE_RE = re.compile(
    r"\b(?:fyi|heads up|just so you know|for your information|update|status|"
    r"i(?:'ve| have) (?:finished|completed|sent|done|pushed|merged)|"
    r"(?:is|are|has been|have been) (?:done|finished|complete|ready|live|merged)|"
    r"wanted to (?:let you know|flag)|noting that)\b",
    re.IGNORECASE,
)


def message_type(text: str) -> str:
    """One of MESSAGE_TYPES, by rule.

    Precedence is deliberate and order-sensitive:

    1. `social` first, and only when the message is *nothing but*
       pleasantries. "Thanks!" is social; "Thanks - can you send it?" is a
       request wearing a thank-you.
    2. `request` next, because an ask embedded in an update is still an ask,
       and missing it is the costlier error for this product.
    3. `commitment` before `update`: "I'll send it Friday" is a promise with
       a deadline, not a status note.
    4. `update` as the default. A message that asks nothing and promises
       nothing is, for our purposes, telling you something.
    """
    stripped = (text or "").strip()
    if not stripped:
        return "update"
    if _SOCIAL_ONLY_RE.match(stripped):
        return "social"
    # Social opener with a short tail, and nothing else going on.
    if (
        _SOCIAL_LEAD_RE.match(stripped)
        and len(stripped.split()) <= _SOCIAL_MAX_WORDS
        and not _REQUEST_RE.search(stripped)
        and not _COMMITMENT_RE.search(stripped)
        and not _UPDATE_RE.search(stripped)
    ):
        return "social"
    if _REQUEST_RE.search(stripped) or _is_imperative(stripped):
        return "request"
    if _COMMITMENT_RE.search(stripped):
        return "commitment"
    if _UPDATE_RE.search(stripped):
        return "update"
    return "update"


def _is_imperative(text: str) -> bool:
    """True if the message opens with a bare imperative ("Send the deck.").

    Uses the backend extractor's spaCy pipeline rather than loading a second
    one. Falls back to False if spaCy is unavailable - a missed imperative
    costs a request classification, which is recoverable; a crash is not.
    """
    try:
        module = _backend_extractor()
        doc = module._get_nlp()(text)
        for sent in doc.sents:
            root = sent.root
            if root.tag_ == "VB" and not any(c.dep_ == "nsubj" for c in root.children):
                return True
            if module._imperative_noun_root(sent) is not None:
                return True
            break  # only the opening sentence decides
    except Exception:  # noqa: BLE001
        return False
    return False


# --------------------------------------------------------------------------
# Concurrent analysis
# --------------------------------------------------------------------------

ADAPTERS: tuple[Any, ...] = (politeness, tone, circa)


@dataclass
class Analysis:
    """Everything the analysis layer knows about one message."""

    message: str
    message_type: str
    extraction: Extraction
    comments: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "message_type": self.message_type,
            "extraction": self.extraction.as_dict(),
            "comments": list(self.comments),
        }


def analyse(text: str, adapters: Iterable[Any] | None = None) -> Analysis:
    """Run every analyser over `text` concurrently and collect the results.

    The message type is settled first, on the calling thread, because the
    extractor needs it to decide which absences are worth reporting. It is a
    handful of regexes plus one spaCy parse, so it is not the bottleneck.
    """
    adapters = tuple(adapters) if adapters is not None else ADAPTERS
    kind = message_type(text)

    tasks: list[Callable[[], Any]] = [lambda: extract(text, kind)]
    tasks += [(lambda a=a: a.predict(text)) for a in adapters]

    with ThreadPoolExecutor(max_workers=len(tasks)) as pool:
        results = list(pool.map(lambda fn: fn(), tasks))

    extraction, comments = results[0], list(results[1:])
    return Analysis(
        message=text, message_type=kind, extraction=extraction, comments=comments
    )
