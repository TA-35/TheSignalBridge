"""Checks the LLM's response before any of it reaches a user.

Two checks, both of which can only fail closed:

1. **Span check.** Every span the response cites must resolve to real text in
   the original message - `message[start:end]` has to equal the quoted text.
   This is the traceability constraint: a claim the user cannot follow back
   into their own message is not a claim we are willing to show.

2. **Entity check.** Every DATE, TIME, PERSON, ORG and CARDINAL spaCy finds
   in the response must also appear in the input. This is the anti-invention
   constraint. An LLM asked to summarise "get this to me soon" will happily
   produce "by Friday", and a fabricated deadline in a workplace tool is
   worse than no tool.

On any failure validate_response() discards the response entirely and returns
templated output built only from extractor spans, with `degraded: true`. Not
partially repaired: if the model invented one date, its other claims have not
earned trust either. pipeline.run() then shows the model what failed and asks
again. Only if that fails too does salvage_response() keep the parts that
pass on their own, each held to the summary's standard - see there for why
that is still safe.

Nothing here logs message text. Failure reasons name the field and the offending
entity type, never the message body - see constraint 3.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from ._lazy import Lazy
from .analysis import Analysis, Extraction

# The entity types that carry checkable facts. Deliberately not the full spaCy
# set: LANGUAGE or NORP appearing in a paraphrase is not an invented fact,
# whereas a date, a person or a number is.
CHECKED_ENTITY_LABELS: frozenset[str] = frozenset(
    {"DATE", "TIME", "PERSON", "ORG", "CARDINAL"}
)

_WORD_NUMBERS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12",
}

# Words spaCy labels CARDINAL that are almost never a quantity claim.
# Measured: "One thing is unclear" and "Send one copy" both tag `one` as
# CARDINAL, and the first is a determiner. Rejecting on it degraded a real
# K3 response whose only sin was ordinary English - and since "one" is
# everywhere in prose, keeping it strict would degrade almost every answer,
# which is a product failure rather than a safe default.
#
# The residual risk is a fabricated singular quantity ("send one copy" when
# the message never said how many). That is a misreading rather than an
# invention, it is low-harm, and the cross-check against the extractor is
# the layer that catches misreadings. Every other number - digits, "two"
# upward, dates, times - stays strict.
_UNCOUNTED_CARDINALS = frozenset({"one", "a", "an", "0", "zero"})

_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")

def _load_nlp() -> Any:
    from .analysis import _backend_extractor

    return _backend_extractor()._get_nlp()


_nlp_holder = Lazy(_load_nlp)


def _get_nlp() -> Any:
    """Reuse the backend extractor's spaCy pipeline rather than loading a second."""
    return _nlp_holder.get()


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------

@dataclass
class ValidationResult:
    ok: bool
    failures: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return self.ok


# --------------------------------------------------------------------------
# Span resolution: turning a quoted string into an exact span
# --------------------------------------------------------------------------

def _all_occurrences(message: str, text: str) -> list[int]:
    out, start = [], message.find(text)
    while start != -1:
        out.append(start)
        start = message.find(text, start + 1)
    return out


# Characters a faithful quote can still get wrong. Measured on GPT-OSS over
# the 120 gold messages: 49 quotes were not character-exact, and 36 of them
# were the message's own words with a hard-wrapped line break typed as a
# space, a straight apostrophe typed curly, or a capital added at the start.
# Two answers lost every claim that way. The other 13 cut words out with
# "..." or reworded the passage, and still fail, as they should.
_SAME_CHARACTER = (
    ("'\N{RIGHT SINGLE QUOTATION MARK}\N{LEFT SINGLE QUOTATION MARK}"
     "\N{MODIFIER LETTER APOSTROPHE}"),
    '"\N{LEFT DOUBLE QUOTATION MARK}\N{RIGHT DOUBLE QUOTATION MARK}',
    "-\N{HYPHEN}\N{NON-BREAKING HYPHEN}\N{FIGURE DASH}\N{EN DASH}\N{EM DASH}",
)
_QUOTE_EQUIVALENTS = {
    char: f"[{re.escape(group)}]" for group in _SAME_CHARACTER for char in group
}


def _loose_pattern(text: str, flags: int = 0) -> re.Pattern[str]:
    """`text` with any run of whitespace matching any other, and the
    typographic forms of quotes and dashes matching each other."""
    parts = []
    for chunk in re.split(r"(\s+)", text.strip()):
        if chunk.isspace():
            parts.append(r"\s+")
        elif chunk:
            parts.append("".join(_QUOTE_EQUIVALENTS.get(c, re.escape(c)) for c in chunk))
    return re.compile("".join(parts), flags)


def resolve_span(
    message: str, text: str, hint: int | None = None
) -> tuple[int, int] | None:
    """Locate `text` in `message`, or return None.

    Exactly first. Failing that, allowing for the differences in
    _QUOTE_EQUIVALENTS, then for case as well. A span found that way still
    covers the message's own characters, and resolve_claim_spans() shows
    those rather than the model's copy, so the reader still sees exactly what
    their message says.

    The LLM quotes; this finds the offsets. That split exists because
    character arithmetic over a 3,000-character email is the thing language
    models are worst at, while quoting is the thing they are best at.

    `hint` is the model's guess at the offset, and it only has to be roughly
    right. Real messages repeat themselves - "Please let us know" appeared
    four times in one email we tested - so a bare find() silently returns the
    wrong occurrence and the span check passes anyway, highlighting the wrong
    paragraph. With several matches and no hint, this refuses rather than
    guesses; with a hint it takes the nearest match.
    """
    if not text:
        return None
    spans = [(start, start + len(text)) for start in _all_occurrences(message, text)]
    if not spans and text.strip():
        spans = ([m.span() for m in _loose_pattern(text).finditer(message)]
                 or [m.span() for m in _loose_pattern(text, re.IGNORECASE).finditer(message)])
    if not spans:
        return None  # the quote is not in the message at all
    if len(spans) == 1:
        return spans[0]
    if hint is None:
        return None  # ambiguous, and nothing to disambiguate with
    return min(spans, key=lambda span: abs(span[0] - hint))


def resolve_claim_spans(
    response: Mapping[str, Any], message: str
) -> tuple[list[dict[str, Any]], list[str]]:
    """Attach an exact span to every claim, dropping the ones that cannot get one."""
    resolved: list[dict[str, Any]] = []
    failures: list[str] = []
    for index, claim in enumerate(response.get("claims") or []):
        if not isinstance(claim, Mapping):
            failures.append(f"claims[{index}]: not an object")
            continue
        text = str(claim.get("text", ""))
        hint = claim.get("span_hint")
        hint = hint if isinstance(hint, int) and not isinstance(hint, bool) else None
        span = resolve_span(message, text, hint)
        if span is None:
            # Never echo the quote - it is user text if it matched, and
            # model text if it did not; either way the field name is enough.
            failures.append(
                f"claims[{index}]: quoted text is not in the message, "
                f"or matches several places with no usable hint"
            )
            continue
        resolved.append({**{k: v for k, v in claim.items() if k != "span_hint"},
                         "text": message[span[0]:span[1]],
                         "span": list(span)})
    return resolved, failures


# --------------------------------------------------------------------------
# Check 1: spans
# --------------------------------------------------------------------------

def iter_spans(node: Any, path: str = "response") -> Iterable[tuple[str, Any, Any]]:
    """Yield (path, span, quoted_text) for every span-bearing object found.

    A span-bearing object is any mapping with a "span" key. The quoted text is
    its "text" or "value" if present, otherwise None (span-only, still checked
    for bounds).
    """
    if isinstance(node, Mapping):
        if "span" in node:
            yield path, node.get("span"), node.get("text", node.get("value"))
        for key, value in node.items():
            yield from iter_spans(value, f"{path}.{key}")
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            yield from iter_spans(value, f"{path}[{index}]")


def check_spans(response: Any, message: str) -> ValidationResult:
    """Every cited span must resolve to real text in `message`."""
    failures: list[str] = []
    for path, span, quoted in iter_spans(response):
        if (
            not isinstance(span, (list, tuple))
            or len(span) != 2
            or not all(isinstance(v, int) and not isinstance(v, bool) for v in span)
        ):
            failures.append(f"{path}: span is not a pair of integers")
            continue
        start, end = span
        if not (0 <= start < end <= len(message)):
            failures.append(f"{path}: span out of bounds")
            continue
        if quoted is not None and message[start:end] != quoted:
            # Never echo either string - one is user text.
            failures.append(f"{path}: quoted text does not match the span")
    return ValidationResult(ok=not failures, failures=failures)


# --------------------------------------------------------------------------
# Check 2: entities
# --------------------------------------------------------------------------

# "1:00 p.m." and "1 p.m." are the same time. Measured: the model wrote the
# second for a message that said the first, and the answer was thrown away.
_ZERO_MINUTES_RE = re.compile(r"(\d):00\b")

# A message that misspells the word its deadline hangs on still gives that
# deadline, and a model that spells it right has not invented one. Measured:
# an Enron email's "tommorow" failed every answer that said "tomorrow" in all
# four runs - repairs included, because the model was being told to remove a
# word the message plainly does contain.
_MISSPELT = {"tommorow": "tomorrow", "tommorrow": "tomorrow", "tomorow": "tomorrow"}
_MISSPELT_RE = re.compile(r"\b(" + "|".join(_MISSPELT) + r")\b")


def _normalise(text: str) -> str:
    text = _ZERO_MINUTES_RE.sub(r"\1", text.lower())
    text = _MISSPELT_RE.sub(lambda match: _MISSPELT[match[1]], text)
    text = _PUNCT_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _variants(entity: str) -> set[str]:
    """Surface forms that should all count as 'present in the input'."""
    base = _normalise(entity)
    out = {base}
    # "2 pm" / "2pm", "Friday." / "Friday"
    out.add(base.replace(" ", ""))
    # spelled-out numbers against digits and vice versa
    for word, digit in _WORD_NUMBERS.items():
        if word in base.split():
            out.add(base.replace(word, digit))
        if digit in base.split():
            out.add(base.replace(digit, word))
    # a leading article is not part of the fact
    for article in ("the ", "a ", "an "):
        if base.startswith(article):
            out.add(base[len(article):])
    # Nor is a leading "around": spaCy takes "around 4 pm" as the TIME when
    # the message wrote "4pm", and that cost a real answer.
    for lead in ("around ", "about ", "approximately ", "roughly ", "by ", "at ",
                 "before ", "until "):
        if base.startswith(lead):
            out.update({base[len(lead):], base[len(lead):].replace(" ", "")})
    # "Makayla Bean's" names the person the message calls "Makayla Bean".
    if base.endswith(" s"):
        out.add(base[:-2])
    return {v for v in out if v}


# Which parts of the response assert facts about the message, and so must not
# contain anything the message lacks.
#
# Not all of it does, and checking the rest is a category error that showed up
# the moment the prompt started asking for interpretation rather than
# extraction:
#
#   summary  - asserts what the message is doing. A fabricated date here is
#              exactly the failure this check exists to catch. CHECKED.
#   text     - a verbatim quote. Already proven verbatim by span resolution,
#              so re-checking its entities can only produce false positives.
#   reading  - explains what a quote means, and legitimately reasons about
#              what is ambiguous: "if they mean close of business day, you
#              have until 5". "the business day" is not a claim the message
#              said that. NOT CHECKED.
#   unstated - questions about what the message does NOT say. Flagging it for
#              containing things absent from the message inverts its purpose:
#              "is Sarah the only one?" was rejected for an invented CARDINAL.
#              NOT CHECKED.
#
# The guarantee that matters is unchanged: every claim still resolves to an
# exact span, and the summary still cannot invent a fact.
FACT_BEARING_KEYS: frozenset[str] = frozenset({"summary"})

# Interpretive fields get a narrower check rather than none.
#
# Exempting them entirely was too broad. A real run on a message with no names
# in it produced the question "is Sarah the only one?" - a fabricated person
# presented to the reader as though the message named them. Constraint 2 lists
# names explicitly, and no amount of interpretive licence covers inventing one.
#
# The distinction that holds: a reading may reason about time and quantity
# ("if they mean close of business", "is this the only ask?") because that is
# hedging about what the message left vague. It may never introduce a PERSON or
# an ORG, because there is nothing vague about whether a name was written.
INTERPRETIVE_KEYS: frozenset[str] = frozenset(
    {"reading", "unstated", "question"}
)
NAME_LABELS: frozenset[str] = frozenset({"PERSON", "ORG"})


def _iter_interpretive_text(node: Any) -> Iterable[str]:
    """Every string under an interpretive key, at any depth."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            if key in INTERPRETIVE_KEYS:
                yield from iter_text(value, _top=False)
            elif key != "span":
                yield from _iter_interpretive_text(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _iter_interpretive_text(value)


def iter_text(node: Any, _top: bool = True) -> Iterable[str]:
    """Every string that asserts something about the message.

    At the top level this selects only the fact-bearing keys. Nested values
    below one of those keys are yielded whole, so a summary shaped as a list
    or object is still covered.
    """
    if _top and isinstance(node, Mapping):
        for key in FACT_BEARING_KEYS:
            if key in node:
                yield from iter_text(node[key], _top=False)
        return
    if isinstance(node, str):
        yield node
    elif isinstance(node, Mapping):
        for key, value in node.items():
            if key != "span":
                yield from iter_text(value, _top=False)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from iter_text(value, _top=False)


# en_core_web_sm's NER is the weak link in this check. Measured on the model
# actually installed here: "Ask Sarah to send it" tags Sarah as PERSON, and
# "Ask Priya Sharma" tags the full name, but "Ask Priya to send it" yields no
# entity at all - a bare non-Anglo given name slips straight through. Since
# constraint 2 names *names* explicitly, NER alone under-delivers on it.
#
# So: any capitalised word in the response that is absent from the input is
# flagged, whether or not spaCy recognised it. This over-triggers by design.
# A false positive costs a degraded answer, which is safe and merely less
# useful; a false negative puts a fabricated colleague's name in front of a
# user, which is the failure this whole layer exists to prevent.
_CAPITALISED_RE = re.compile(r"\b[A-Z][a-z]{1,}\b")

# Capitalised words that are not names. Sentence-initial words are excluded
# separately, via spaCy's sentence boundaries.
_CAPITALISED_ALLOWED = frozenset({
    "i", "ok", "okay", "yes", "no", "please", "thanks", "thank", "hi", "hello",
    "hey", "the", "this", "that", "they", "there", "then", "it", "its", "if",
    "when", "who", "what", "why", "how", "where", "showing", "purpose",
    "priority", "background", "who", "by", "unclear", "found", "monday",
    "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
})


def check_entities(response: Any, message: str) -> ValidationResult:
    """No DATE, TIME, PERSON, ORG, CARDINAL or unexplained capitalised word
    may appear that the input lacks."""
    failures: list[str] = []
    try:
        nlp = _get_nlp()
    except Exception:  # noqa: BLE001
        # Without spaCy this check cannot run. Fail closed: an unverifiable
        # response is treated as unverified.
        return ValidationResult(ok=False, failures=["entity check unavailable"])

    haystack = _normalise(message)
    haystack_tight = haystack.replace(" ", "")

    def present(value: str) -> bool:
        return any(v in haystack or v in haystack_tight for v in _variants(value))

    # Names, anywhere they appear in interpretive text.
    #
    # Both passes, for the same reason the summary needs both: en_core_web_sm
    # tags "Sarah" as PERSON but returns nothing at all for a bare "Priya", so
    # NER alone would catch one invented colleague and miss another.
    for text in _iter_interpretive_text(response):
        if not text.strip():
            continue
        doc = nlp(text)
        for ent in doc.ents:
            if ent.label_ in NAME_LABELS and not present(ent.text):
                failures.append(f"invented {ent.label_} in interpretation: "
                                f"{ent.text!r}")
        for token in doc:
            if token.is_sent_start or not _CAPITALISED_RE.fullmatch(token.text):
                continue
            if token.text.lower() in _CAPITALISED_ALLOWED or present(token.text):
                continue
            failures.append(f"unverified capitalised word in interpretation: "
                            f"{token.text!r}")

    for text in iter_text(response):
        if not text.strip():
            continue
        doc = nlp(text)

        for ent in doc.ents:
            if ent.label_ not in CHECKED_ENTITY_LABELS:
                continue
            if (ent.label_ == "CARDINAL"
                    and _normalise(ent.text) in _UNCOUNTED_CARDINALS):
                continue
            if present(ent.text):
                continue
            # Name the type, never the message. The entity itself came from
            # the model's own output, so it is safe to name.
            failures.append(f"invented {ent.label_}: {ent.text!r}")

        for token in doc:
            if token.is_sent_start or not _CAPITALISED_RE.fullmatch(token.text):
                continue
            if token.text.lower() in _CAPITALISED_ALLOWED or present(token.text):
                continue
            failures.append(f"unverified capitalised word: {token.text!r}")

    return ValidationResult(ok=not failures, failures=sorted(set(failures)))


# GPT-OSS writes U+2011 (non-breaking hyphen) in compounds and U+202F (narrow
# no-break space) inside times, and spaCy reads "follow-up" or "real-name"
# written with that hyphen as an ORG. On the gold set, 5 of 19 rejected answers had
# nothing else wrong. Prose is made plain before it is checked - and so
# before it is shown, which costs the reader nothing. A claim's `text` is
# left alone: it is matched against the message, not checked.
_PLAIN = str.maketrans({
    "\N{HYPHEN}": "-",
    "\N{NON-BREAKING HYPHEN}": "-",
    "\N{NO-BREAK SPACE}": " ",
    "\N{THIN SPACE}": " ",
    "\N{NARROW NO-BREAK SPACE}": " ",
    "\N{LEFT SINGLE QUOTATION MARK}": "'",
    "\N{RIGHT SINGLE QUOTATION MARK}": "'",
})


def _plain_prose(node: Any, key: str | None = None) -> Any:
    if isinstance(node, str):
        return node if key == "text" else node.translate(_PLAIN)
    if isinstance(node, Mapping):
        return {k: _plain_prose(v, k) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [_plain_prose(v, key) for v in node]
    return node


# --------------------------------------------------------------------------
# Degraded fallback
# --------------------------------------------------------------------------

_FIELD_LABELS = {
    "purpose": "Purpose",
    "required_action": "What needs doing",
    "responsible_person": "Who",
    "deadline": "By when",
    "priority": "Priority",
    "context": "Background",
}


# Asked when there is no model answer to ask it better. Phrased as the reader
# would type them, to match what the model is told to produce - the degraded
# panel should read like a quieter version of the same panel, not a different
# feature.
_GAP_QUESTIONS: dict[str, str] = {
    "purpose": "What is this actually about?",
    "required_action": "What exactly needs to be done?",
    "responsible_person": "Who is meant to do this - me, or someone else?",
    "deadline": "When do you need this by?",
    "priority": "How urgent is this against what I am already doing?",
    "context": "Is there background here I am missing?",
}
_DEFAULT_GAP = "Can you say more about this?"


def templated_output(analysis: Analysis, reasons: Iterable[str] = ()) -> dict[str, Any]:
    """Output built only from extractor spans - no model text at all.

    Every claim is a verbatim quotation of the user's own message, so this is
    trivially traceable and cannot contain an invented entity.
    """
    extraction: Extraction = analysis.extraction

    # One claim per ask, then the other fields. Falling back to a single
    # action would quietly drop four of the five asks in a real email - the
    # degraded path has to stay honest about how much the message contains.
    claims = [
        {
            "field": "required_action",
            "label": _FIELD_LABELS["required_action"],
            "text": action.value,
            "span": list(action.span),
        }
        for action in extraction.actions
    ]
    claims += [
        {
            "field": found.field,
            "label": _FIELD_LABELS.get(found.field, found.field),
            "text": found.value,
            "span": list(found.span),
        }
        for key, found in extraction.found.items()
        if key != "required_action"
    ]
    return {
        "degraded": True,
        "degraded_reason": sorted(set(reasons)),
        "message_type": analysis.message_type,
        "claims": claims,
        # Same shape as the model's `missing`, deliberately. An earlier
        # divergence between two degraded paths meant callers had to know
        # which one they got; a list of bare field names here against a list
        # of objects there would be the same bug in a new place. The wording
        # is canned rather than generated, which is exactly what makes it
        # safe in a path that exists because the model could not be trusted.
        "missing": [
            {"field": field, "question": _GAP_QUESTIONS.get(field, _DEFAULT_GAP)}
            for field in extraction.missing
        ],
        # Counts live in their own integer fields, never in the prose. An
        # earlier version wrote "3 items found, 2 unclear" into the summary
        # and the fallback failed its own entity check - those digits are
        # CARDINALs absent from the user's message. The fallback has to pass
        # the check that rejected the model, or it is not a safe fallback.
        "found_count": len(claims),
        "missing_count": len(extraction.missing),
        "summary": "Showing only what could be read directly from the message.",
    }


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def validate_response(
    response: Any, message: str, analysis: Analysis
) -> dict[str, Any]:
    """Return the response if every check passes, otherwise degraded output.

    Order matters: spans are resolved from quoted text first, so the span
    check runs against offsets this module computed rather than offsets the
    model guessed at. A claim whose quote is absent from the message, or
    repeated with no usable hint, is a failure - not something to paper over.

    The returned dict always carries a `degraded` flag so the frontend can
    tell the user it is looking at a reduced answer.
    """
    if not isinstance(response, Mapping):
        return templated_output(analysis, ["response was not an object"])

    response = _plain_prose(response)
    claims, resolve_failures = resolve_claim_spans(response, message)

    # An unresolvable quote and an invented entity are different failures and
    # deserve different responses.
    #
    # A claim whose quote is not in the message is self-identifying as
    # unusable: it can be dropped precisely, and doing so UPHOLDS the
    # traceability rule rather than bending it - everything still shown
    # carries an exact verified span. It says nothing about the claims that
    # did verify.
    #
    # An invented entity is different in kind: the model asserted a fact from
    # nowhere, so its whole reading is suspect and the response is discarded
    # entirely. That distinction stays below.
    #
    # Measured on llama-3.2-11b: it reliably produces three or four good
    # claims then fabricates one more. Failing the whole response threw away
    # four verified claims to punish the fifth, degrading 4 runs in 6.
    if resolve_failures and not claims:
        # Nothing survived - there is no partial answer to give.
        return templated_output(analysis, resolve_failures)

    # A field cannot be both settled and unsettled. The prompt says so, but a
    # panel that lists "deadline" as covered directly above a checkbox asking
    # for the deadline reads as a broken page, so it is enforced here rather
    # than hoped for. Claims win: they carry a verified span, and the gap
    # entry carries nothing.
    #
    # Dropping a claim for being unresolvable can reopen a gap, which is why
    # this runs against the surviving claims rather than the model's original
    # list - a deadline claim that failed verification leaves the deadline
    # genuinely unsettled, and the checkbox should come back.
    settled = {c.get("field") for c in claims}
    gaps = [
        gap
        for gap in (response.get("missing") or [])
        if isinstance(gap, Mapping) and gap.get("field") not in settled
    ]

    candidate = {**response, "claims": claims, "missing": gaps}
    spans = check_spans(candidate, message)
    entities = check_entities(candidate, message)

    if spans.ok and entities.ok:
        result = {**candidate, "degraded": False}
        if resolve_failures:
            # Not degraded - every claim shown is verified - but the caller
            # should know some were dropped, and how many.
            result["dropped_claims"] = len(resolve_failures)
            result["dropped_reason"] = resolve_failures
        return result

    return templated_output(analysis, spans.failures + entities.failures)


# --------------------------------------------------------------------------
# Last resort: the parts that pass on their own
# --------------------------------------------------------------------------

def _holds_up(text: str, message: str) -> bool:
    """`text` held to the summary's standard: no date, time, number, name or
    capitalised word that the message lacks."""
    return check_entities({"summary": text}, message).ok


def salvage_response(response: Any, message: str) -> dict[str, Any] | None:
    """The verified parts of an answer that failed as a whole, or None.

    validate_response() throws a whole answer away for one invented fact, on
    the reasoning that the rest has not earned trust. That stays the first
    response: pipeline.run() shows the model what failed and asks again
    before this is reached. This is for when it still fails, and the only
    alternative left is the extractor's canned reading.

    What earns the rest back is checking each part on its own, and more
    strictly than validate_response() does. Every reading, question and
    unstated item is held to the summary's standard, so no date, time, number
    or name the message lacks survives anywhere. The licence a reading
    normally has to hedge about time ("if they mean close of business") is
    withdrawn, because this answer has already shown that it adds facts.
    Without that, an invented "Friday" cut from the summary would live on in
    a reading, where dates are not otherwise checked.

    Not degraded - everything kept is verified - but marked `partial`, with
    what was cut and why, the same way dropped claims already are. None when
    no claim survives: a summary with no verified quote under it rests on
    nothing the reader can check.
    """
    if not isinstance(response, Mapping):
        return None
    response = _plain_prose(response)
    claims, unresolved = resolve_claim_spans(response, message)
    kept = [c for c in claims if _holds_up(str(c.get("reading", "")), message)]
    if not kept:
        return None
    summary = str(response.get("summary") or "")
    if not _holds_up(summary, message):
        summary = ""

    settled = {c.get("field") for c in kept}
    gaps = [
        gap
        for gap in (response.get("missing") or [])
        if isinstance(gap, Mapping) and gap.get("field") not in settled
        and _holds_up(str(gap.get("question", "")), message)
    ]
    unstated = [u for u in (response.get("unstated") or [])
                if _holds_up(str(u), message)]
    candidate = {**response, "summary": summary, "claims": kept,
                 "missing": gaps, "unstated": unstated}

    # What is left still has to pass the ordinary checks as a whole.
    if not (check_spans(candidate, message).ok
            and check_entities(candidate, message).ok):
        return None
    cut = unresolved + check_entities({**response, "claims": claims}, message).failures
    return {
        **candidate,
        "degraded": False,
        "partial": True,
        "dropped_claims": len(response.get("claims") or []) - len(kept),
        "dropped_reason": sorted(set(cut)),
    }
