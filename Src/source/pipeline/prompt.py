"""Builds the LLM prompt from a message and its analysis.

Templates live in prompts/*.txt, not in string literals here, so the wording
can be edited and diffed without touching Python. This module only decides
what goes into the placeholders.

The response schema lives here too: the LLM is given a JSON schema rather
than asked politely for JSON, so malformed output is a transport failure
rather than a parsing gamble.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping

from .analysis import FIELDS, Analysis
from .config import PipelineConfig, load

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

MODES = {"review": "review.txt", "form": "form.txt"}

# What the model must return. `span` is what makes a claim checkable, so it is
# required on every claim - a claim without one cannot survive the validator.
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "One or two sentences on what this message is doing. "
                           "Must not contain any date, name or number absent "
                           "from the message.",
        },
        "claims": {
            "type": "array",
            "description": "Grounded observations, each tied to a span.",
            "items": {
                "type": "object",
                "properties": {
                    # Constrained to our own field names. Left as a free
                    # string, a real K3 run invented "request" and "status",
                    # which match nothing the extractor produces - so the
                    # cross-check compared zero fields and reported
                    # agreement=None, looking like success rather than a
                    # comparison that never ran.
                    "field": {"type": "string", "enum": list(FIELDS)},
                    "text": {
                        "type": "string",
                        "description": "Exact characters at `span`.",
                    },
                    "span_hint": {
                        "type": "integer",
                        "description": "Roughly where `text` starts, in "
                                       "characters. An estimate is fine - it "
                                       "is only used to pick between repeated "
                                       "occurrences. The exact span is "
                                       "computed from `text`.",
                    },
                    "reading": {
                        "type": "string",
                        "description": "What this tells the reader.",
                    },
                },
                "required": ["field", "text", "span_hint", "reading"],
                "additionalProperties": False,
            },
        },
        "unstated": {
            "type": "array",
            "description": "What the message does not say, phrased as a "
                           "question the reader could ask.",
            "items": {"type": "string"},
        },
    },
    "required": ["summary", "claims", "unstated"],
    "additionalProperties": False,
}


def _read_template(mode: str) -> str:
    try:
        name = MODES[mode]
    except KeyError:
        raise ValueError(f"unknown mode {mode!r}; expected one of {sorted(MODES)}") from None
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def _format_extracted(analysis: Analysis) -> str:
    extraction = analysis.extraction
    actions = extraction.actions
    others = [v for k, v in extraction.found.items() if k != "required_action"]

    if not actions and not others:
        return "  (nothing could be located with a verifiable span)"

    lines = []
    # Every ask, numbered. A message with five asks must not be summarised as
    # though it had one - that is the single most misleading thing this
    # pipeline could tell a reader.
    if len(actions) > 1:
        lines.append(f"  required_action - {len(actions)} separate asks in this message:")
        lines += [
            f"      {i}. \"{a.value}\"  span=[{a.span[0]}, {a.span[1]}]"
            for i, a in enumerate(actions, 1)
        ]
    elif actions:
        a = actions[0]
        lines.append(f"  - required_action: \"{a.value}\"  span=[{a.span[0]}, {a.span[1]}]")

    lines += [
        f"  - {item.field}: \"{item.value}\"  span=[{item.span[0]}, {item.span[1]}]"
        for item in others
    ]
    return "\n".join(lines)


def _format_missing(analysis: Analysis) -> str:
    missing = analysis.extraction.missing
    if not missing:
        return "  (nothing expected of this message type is absent)"
    return "\n".join(f"  - {name}" for name in missing)


def _format_comments(
    comments: Iterable[Mapping[str, Any]], min_confidence: float
) -> str:
    """Render the model comments, or nothing at all when the flag is off.

    Confidence is stated next to each comment and the model is told how to
    use it, because the three models disagree about how much they should be
    believed - one is capped as out of domain, one caps its own weakest
    class, and any of them may be unavailable.
    """
    usable = [
        c for c in comments
        if float(c.get("confidence", 0.0)) > min_confidence
    ]
    if not usable:
        return ""

    lines = [
        "",
        "WHAT THREE SMALL MODELS SAID ABOUT THIS MESSAGE.",
        "Each carries a confidence from 0 to 1 and a note on its own known",
        "weaknesses. Weigh them accordingly: a comment at 0.3 is a hint worth",
        "considering, not a fact. Where a model contradicts the message text,",
        "the message text wins - these models are advisory, and none of them",
        "was trained on workplace email. They are not evidence for a claim;",
        "only a span is. Never quote a model's note back to the user.",
        "",
    ]
    for comment in usable:
        lines.append(
            f"  - {comment.get('model')}: {comment.get('label')} "
            f"(confidence {float(comment.get('confidence', 0.0)):.2f})"
        )
        note = str(comment.get("note", "")).strip()
        if note:
            lines.append(f"      note: {note}")
    lines.append("")
    return "\n".join(lines)


def build(
    analysis: Analysis,
    mode: str = "review",
    config: PipelineConfig | None = None,
) -> str:
    """Render the prompt for `analysis`.

    When config.include_model_comments is False the three comments are left
    out entirely and everything else is byte-identical, which is what makes
    the with/without comparison a fair one.
    """
    config = config or load()
    template = _read_template(mode)
    extracted = (
        _format_extracted(analysis) if config.include_extracted_spans
        else "  (not provided - read the message yourself)"
    )
    missing = (
        _format_missing(analysis) if config.include_extracted_spans
        else "  (not provided - decide for yourself what this message leaves out)"
    )
    comments = (
        _format_comments(analysis.comments, config.min_comment_confidence)
        if config.include_model_comments
        else ""
    )
    # Restated in the prompt text because schema enforcement is not uniform:
    # kimi-k3 honours the `field` enum, llama-3.2-11b ignores it and returns
    # claims with no field at all - which silently disables the cross-check,
    # since there is nothing to match against the extractor's findings.
    return template.format(
        fields="\n".join(f"  {name}" for name in FIELDS),
        message_type=analysis.message_type,
        message=analysis.message,
        extracted=extracted,
        missing=missing,
        comments=comments,
    )
