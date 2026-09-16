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

On any failure the response is discarded entirely and replaced with templated
output built only from extractor spans, with `degraded: true`. Not partially
repaired: if the model invented one date, its other claims have not earned
trust either.

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


def resolve_span(
    message: str, text: str, hint: int | None = None
) -> tuple[int, int] | None:
    """Locate `text` in `message` exactly, or return None.

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
    occurrences = _all_occurrences(message, text)
    if not occurrences:
        return None  # the quote is not in the message at all
    if len(occurrences) == 1:
        start = occurrences[0]
    elif hint is None:
        return None  # ambiguous, and nothing to disambiguate with
    else:
        start = min(occurrences, key=lambda i: abs(i - hint))
    return start, start + len(text)


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

def _normalise(text: str) -> str:
    text = _PUNCT_RE.sub(" ", text.lower())
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
    return {v for v in out if v}


def iter_text(node: Any) -> Iterable[str]:
    """Every string in the response, wherever it is nested."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, Mapping):
        for key, value in node.items():
            if key != "span":
                yield from iter_text(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from iter_text(value)


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
        "missing": list(extraction.missing),
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

    candidate = {**response, "claims": claims}
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
