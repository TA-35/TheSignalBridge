"""Extraction engine for message decoding.

Design principle (per the "never invents meaning" rule in
docs/api-contract.md): this is extractive, not generative. Every
FieldResult with specified=True carries a `span` that is a verbatim
character range into the *original* message. If a value can't be
grounded in the source text, the field is left unspecified rather than
guessed.

Uses spaCy's pretrained en_core_web_sm (public model, not fine-tuned on
any user data) for sentence segmentation, POS/dependency tags, and
DATE/TIME entities. Everything on top is deterministic rules, so outputs
are reproducible and explainable - no LLM call in this version.

Field names here are the engine's own (`task_to_do`); the mapping to the
API contract's `task` happens in ai_decoder.py.
"""
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import spacy

FIELD_NAMES = ["time", "task_to_do", "deadline", "for_whom"]

DEADLINE_TRIGGERS = ["by", "due", "before", "no later than", "until"]
TIME_TRIGGERS = ["at", "on", "during"]
REQUEST_MARKERS = [
    "please", "can you", "could you", "would you", "need you to",
    "kindly", "make sure you", "don't forget to",
    # Asks to a group or to nobody in particular: "could everyone pack their
    # desks by Tuesday?" found no task at all.
    "could everyone", "can everyone", "would everyone",
    "could someone", "can someone", "could anyone", "can anyone",
]
FOR_WHOM_ROLE_WORDS = {
    "client", "team", "manager", "customer", "boss", "committee",
    "board", "department", "group",
}

_MEANINGFUL_WORD_RE = re.compile(r"[A-Za-z]{2,}")

_AUX_LEMMAS = {
    "be", "do", "have", "can", "could", "would", "will", "shall",
    "may", "might", "must", "need", "let", "please",
}

# Loaded lazily so importing this module (and the Flask app) stays cheap;
# the model is ~12MB and only the decode route needs it.
_nlp = None


def _get_nlp():
    global _nlp
    if _nlp is None:
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


@dataclass
class FieldResult:
    """One extracted field.

    `span` is the [start, end) character offset into the *original* message
    for `value`. That is what lets the frontend highlight the exact
    substring the field came from. If a field is not specified, value and
    span are both None - never filled in with an inferred guess.
    """

    value: Optional[str] = None
    span: Optional[List[int]] = None
    specified: bool = False


def is_meaningless(text: str) -> bool:
    """True if there's nothing here worth analysing.

    Operational definition: fewer than 3 alphabetic word-tokens of length
    >= 2 after stripping. Catches empty input and punctuation/number-only
    input. Does not catch genuine gibberish English-looking words
    (e.g. "asdf qwer zxcv") - a known limitation, not silently handled.
    """
    stripped = text.strip()
    if not stripped:
        return True
    words = _MEANINGFUL_WORD_RE.findall(stripped)
    return len(words) < 3


def _preceding_window(text: str, start: int, chars: int = 20) -> str:
    return text[max(0, start - chars):start].lower()


# A time has to contain something time-shaped. spaCy tags "the minutes" (of a
# meeting) as TIME, and the task was then cut before it: "send me the minutes
# from Tuesday by 5pm" came out as the task "send me". Same rule as
# Src/source/pipeline/analysis.py's _TIME_SHAPED_RE.
_TIME_SHAPED_RE = re.compile(
    r"\d"
    # Every day, whole or short: "Tuesday" is tue + s + day, "Saturday" sat + ur + day.
    r"|\b(?:mon|tues?|wed(?:nes|s)?|thu(?:rs?)?|fri|sat(?:ur)?|sun)(?:day)?s?\b"
    r"|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\b"
    r"|\b(?:today|tomorrow|tonight|yesterday|noon|midnight|morning|"
    r"afternoon|evening|week|weeks|month|months|day|days|hour|hours|"
    r"eod|cob|asap|quarter|semester|term|deadline|now)\b",
    re.IGNORECASE,
)

# "the report from last week", "the invoice from March": the date says which
# thing is meant, not when to act, so it is neither the time nor the deadline,
# and the task must not be cut short in front of it.
_DESCRIBES_A_THING = {"from", "of", "since"}


def _describes_a_thing(text: str, start: int) -> bool:
    before = re.search(r"([A-Za-z]+)\s*$", text[:start])
    return bool(before) and before.group(1).lower() in _DESCRIBES_A_THING


def _extract_time_and_deadline(doc, text: str) -> Tuple[FieldResult, FieldResult]:
    time_result = FieldResult()
    deadline_result = FieldResult()

    for ent in doc.ents:
        if ent.label_ not in {"TIME", "DATE"}:
            continue
        if not _TIME_SHAPED_RE.search(ent.text) or _describes_a_thing(text, ent.start_char):
            continue
        window = _preceding_window(text, ent.start_char)

        if any(trig in window for trig in DEADLINE_TRIGGERS) and not deadline_result.specified:
            deadline_result = FieldResult(
                value=ent.text, span=[ent.start_char, ent.end_char], specified=True
            )
        elif not time_result.specified:
            # No deadline trigger nearby -> treat as the general "when",
            # regardless of whether spaCy tagged it TIME or DATE. Only an
            # explicit deadline trigger earns the "deadline" label.
            time_result = FieldResult(
                value=ent.text, span=[ent.start_char, ent.end_char], specified=True
            )

    return time_result, deadline_result


# Words left dangling once a trailing clause is cut off ("...report for the"
# -> "...report"). Trimmed from the right so the span stays verbatim.
_TASK_TRAILING_NOISE = {
    "for", "by", "at", "on", "before", "until", "due", "to",
    "the", "a", "an", "sometime", "and", "then", "or", "but", "so",
    # Trailing politeness is not part of the task ("Tighten it, please").
    "please", "thanks", "kindly",
}

# Sentence-final punctuation is not part of the task text.
_TASK_TRAILING_PUNCT = " \t\n.,;:!?-"


# Asks that spaCy's small model tags as something other than a verb when they
# follow a request marker. Only trusted in that position.
_MISTAGGED_VERBS = {
    "forward", "email", "text", "ping", "message", "flag", "loop", "book", "file",
    "print", "chase", "action", "schedule", "sign", "copy", "cc", "update", "proof",
    "circulate", "share", "draft", "order",
}


def _first_action_verb(sent, min_idx: Optional[int] = None):
    """First real verb in the sentence, skipping the request scaffolding.

    "Could you review..." -> review, not "Could". Auxiliaries and modals
    carry no task content, so they are never the task's head.

    `min_idx` starts the search after the request marker, so softeners
    with verbs of their own ("when you get a chance, could you...") do
    not hand back their own verb as the task.
    """
    for token in sent:
        if min_idx is not None and token.idx < min_idx:
            continue
        if token.pos_ == "VERB" and token.lemma_.lower() not in _AUX_LEMMAS:
            return token
        # Right after "please" / "could you", a word spaCy gets wrong:
        # "Please forward the invoice" tags "forward" as an adverb, and the
        # whole ask was lost.
        if (
            min_idx is not None
            and token.is_alpha
            and token.lower_ in _MISTAGGED_VERBS
            and not any(t.is_alpha for t in sent if min_idx <= t.idx < token.idx)
        ):
            return token
    # Nothing after the marker (e.g. "Tighten the numbers, please.") -
    # fall back to scanning the whole sentence.
    if min_idx is not None:
        return _first_action_verb(sent)
    return None


def _trim_task(text: str, start: int, end: int) -> Tuple[str, int]:
    """Trim trailing punctuation and dangling function words.

    Returns (value, end_offset) so the caller can keep the span exact -
    only the right edge ever moves, so text[start:end] == value holds.
    """
    while end > start:
        chunk = text[start:end]
        stripped = chunk.rstrip(_TASK_TRAILING_PUNCT)
        if stripped != chunk:
            end = start + len(stripped)
            continue
        last = re.search(r"([A-Za-z']+)$", chunk)
        if last and last.group(1).lower() in _TASK_TRAILING_NOISE:
            end = start + last.start(1)
            continue
        break
    return text[start:end], end


# Sentence-initial nouns that open a message rather than ask for something.
# spaCy gives these the same shape as a mis-tagged imperative, so they have to
# be named or "Thanks for your help" becomes a task.
_NOT_IMPERATIVE = {
    "thanks", "thank", "hi", "hello", "hey", "regards", "cheers",
    "morning", "afternoon", "fyi", "ps",
}


def _imperative_noun_root(sent):
    """Recover an imperative that spaCy tagged as a noun.

    Verbs that are also nouns ("loop in whoever owns it", "flag it to Sam")
    get tagged NOUN when they open a sentence, so the imperative test in
    _request_anchor misses them. A bare sentence-initial noun root with no
    determiner is the recoverable shape; the greeting list excludes the
    false positives that look identical.
    """
    root = sent.root
    if root.pos_ != "NOUN" or root.lower_ in _NOT_IMPERATIVE:
        return None
    if any(child.dep_ == "det" for child in root.children):
        return None
    if any(tok.pos_ not in {"ADV", "PUNCT"} for tok in sent if tok.i < root.i):
        return None
    return root


def _request_anchor(sent) -> Optional[int]:
    """Where the ask starts in this sentence, or None if it isn't one.

    A request marker anchors after itself ("could you |take a look"); an
    imperative sentence anchors at its start. Sentences that are neither
    are not asks at all, and never produce a task.
    """
    lower = sent.text.lower()
    hits = [(lower.find(m), m) for m in REQUEST_MARKERS if m in lower]
    if hits:
        offset, marker = min(hits)
        return sent.start_char + offset + len(marker)

    root = sent.root
    if root.tag_ == "VB" and not any(child.dep_ == "nsubj" for child in root.children):
        return sent.start_char
    return None


def _task_verbs(doc) -> List:
    """Every distinct action being asked for, in document order."""
    verbs = []
    for sent in doc.sents:
        anchor = _request_anchor(sent)
        if anchor is not None:
            head = _first_action_verb(sent, anchor if anchor > sent.start_char else None)
        elif sum(tok.is_alpha for tok in sent) >= 2:
            # One word on a line ("Link -->" above a URL) is a label, not an ask.
            head = _imperative_noun_root(sent)
        else:
            head = None
        if head is None:
            continue

        group = [head]
        # One marker can cover several asks: "review the deck and tighten
        # the numbers" is two tasks, not one.
        for child in head.children:
            if (
                child.dep_ == "conj"
                and child.pos_ == "VERB"
                and child.lemma_.lower() not in _AUX_LEMMAS
            ):
                group.append(child)
        verbs.extend(group)

    # Dedupe while keeping document order - a verb can be reached twice when
    # sentences overlap markers.
    seen = set()
    ordered = []
    for verb in sorted(verbs, key=lambda t: t.idx):
        if verb.idx not in seen:
            seen.add(verb.idx)
            ordered.append(verb)
    return ordered


def extract_task_clauses(text: str, doc=None, boundaries: Optional[List[int]] = None) -> List[FieldResult]:
    """Every ask in the message, one FieldResult per bullet.

    Each clause runs from its action verb to whichever comes first: the next
    ask, one of the other fields, or the end of its sentence. Spans stay
    verbatim, so text[start:end] == value for every result.
    """
    if doc is None:
        doc = _get_nlp()(text)
    if boundaries is None:
        boundaries = []

    verbs = _task_verbs(doc)
    clauses = []
    for i, verb in enumerate(verbs):
        start = verb.idx
        end = verb.sent.end_char
        if i + 1 < len(verbs):
            end = min(end, verbs[i + 1].idx)
        for boundary in boundaries:
            if start < boundary < end:
                end = boundary

        value, end = _trim_task(text, start, end)
        if value:
            clauses.append(FieldResult(value=value, span=[start, end], specified=True))
    return clauses


def _extract_task_to_do(doc, text: str, boundaries: List[int]) -> FieldResult:
    """The first ask, for the single-task `elements` view of the contract."""
    clauses = extract_task_clauses(text, doc, boundaries)
    return clauses[0] if clauses else FieldResult()


_FOR_PROPER_NOUN_RE = re.compile(r"\bfor\s+((?:[A-Z][\w'-]*\s*){1,3})")
_FOR_ROLE_RE = re.compile(r"\bfor\s+(?:the\s+)?([a-z]+)", re.IGNORECASE)

# "the slides for Friday" says when, not who: a capitalised day, month or
# time word after "for" is not a person. Seen on a real message, where the
# page then showed "For whom: Friday".
_FOR_NOT_A_PERSON = frozenset({
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "mon", "tue", "tues", "wed", "thu", "thur", "thurs", "fri", "sat", "sun",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "today", "tomorrow", "tonight", "tmrw", "eod", "cob", "noon", "christmas", "easter",
    "q1", "q2", "q3", "q4",
})


def _extract_for_whom(doc, text: str) -> FieldResult:
    for m in _FOR_PROPER_NOUN_RE.finditer(text):
        value = m.group(1).strip()
        if value.split()[0].lower().rstrip(".,") in _FOR_NOT_A_PERSON:
            continue
        start = m.start(1)
        end = start + len(value)
        return FieldResult(value=value, span=[start, end], specified=True)

    for m in _FOR_ROLE_RE.finditer(text):
        word = m.group(1).lower()
        if word in FOR_WHOM_ROLE_WORDS:
            start, end = m.span(1)
            return FieldResult(value=text[start:end], span=[start, end], specified=True)

    return FieldResult()


def extract_all(text: str) -> Tuple[Dict[str, FieldResult], List[FieldResult]]:
    """One parse, both views: the single-task `fields` map and every clause.

    Returns (fields, clauses). `fields` is the v1 shape - one value per
    field, task being the first ask. `clauses` is every ask in the message.
    """
    doc = _get_nlp()(text)

    time_result, deadline_result = _extract_time_and_deadline(doc, text)
    for_whom_result = _extract_for_whom(doc, text)

    # Where the other fields start - a task clause stops before them.
    boundaries = sorted(
        r.span[0]
        for r in (time_result, deadline_result, for_whom_result)
        if r.specified and r.span
    )
    clauses = extract_task_clauses(text, doc, boundaries)

    fields = {
        "time": time_result,
        "task_to_do": clauses[0] if clauses else FieldResult(),
        "deadline": deadline_result,
        "for_whom": for_whom_result,
    }
    # Guard against a future field-name typo silently dropping a column.
    assert set(fields.keys()) == set(FIELD_NAMES)
    return fields, clauses


def extract_fields(text: str) -> Dict[str, FieldResult]:
    return extract_all(text)[0]
