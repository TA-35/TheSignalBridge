"""End to end: message in, validated JSON out.

analyse -> build prompt -> call the LLM -> validate -> return.

Every exit from this function is safe to show a user. If the LLM is
unreachable, returns junk, cites a span that does not exist, or invents a
date, the caller gets templated output built from extractor spans with
`degraded: true` - never an exception, and never unvalidated model text.
"""
from __future__ import annotations

from typing import Any

from .analysis import analyse
from .crosscheck import compare
from .config import PipelineConfig, load
from .llm import LLMError, complete
from .prompt import build
from .validator import templated_output, validate_response


def _no_cross_check(reason: str) -> dict[str, Any]:
    """The cross-check's shape when it could not meaningfully run."""
    return {"comparisons": [], "agreement_rate": None,
            "disagreements": [], "skipped": reason}


def run(
    message: str,
    mode: str = "review",
    config: PipelineConfig | None = None,
    llm: Any = None,
) -> dict[str, Any]:
    """Analyse `message`, ask the LLM about it, and validate the answer.

    `llm` overrides the transport for tests; it must accept (prompt, config)
    and return a raw string.
    """
    config = config or load()

    # Guard before analysing: the 111KB case spends 3.3s in spaCy before it
    # would even reach the model. Length is reported, never the message.
    if len(message) > config.max_message_chars:
        return {
            "degraded": True,
            "degraded_reason": [
                f"message is {len(message)} characters; the limit is "
                f"{config.max_message_chars}"
            ],
            "message_type": None,
            "claims": [],
            "missing": [],
            "found_count": 0,
            "missing_count": 0,
            "summary": "This message is too long to analyse.",
            "cross_check": _no_cross_check("message exceeded the length limit"),
            "llm_attempts": 0,
            "model": config.llm.model,
            "model_comments_included": config.include_model_comments,
            "extracted_spans_in_prompt": config.include_extracted_spans,
        }

    analysis = analyse(message)

    try:
        result = complete(build(analysis, mode, config), config.llm, caller=llm)
    except LLMError as exc:
        # The failure reason names the failure class, never the message.
        # Same shape as every other return: a caller reading `cross_check`
        # must not have to know which degraded path it took.
        return {
            **templated_output(analysis, [str(exc)]),
            "cross_check": _no_cross_check("LLM unreachable"),
            "llm_attempts": 0,
            "model": config.llm.model,
            "model_comments_included": config.include_model_comments,
            "extracted_spans_in_prompt": config.include_extracted_spans,
        }

    validated = validate_response(result.data, message, analysis)

    # The extractor ran concurrently regardless of whether its spans went
    # into the prompt, so there is a second reading to compare against. A
    # disagreement is not a verdict - the extractor has its own bugs - it is
    # a flag that two methods read the same sentence differently, which is
    # worth showing rather than hiding.
    #
    # Only on an undegraded response, though. Degraded output IS the
    # extractor's own claims, so comparing it against the extractor compares
    # a thing to itself and reports perfect agreement - a number that looks
    # like success and means nothing. Observed live: a llama response that
    # failed validation still reported agreement 1.0 across four fields.
    crosscheck = (
        compare(validated.get("claims") or [], analysis).as_dict()
        if not validated.get("degraded")
        else _no_cross_check("response degraded - fallback is the extractor itself")
    )

    return {
        **validated,
        "cross_check": crosscheck,
        "llm_attempts": result.attempts,
        "model": result.model,
        "model_comments_included": config.include_model_comments,
        "extracted_spans_in_prompt": config.include_extracted_spans,
    }
