"""End to end: message in, validated JSON out.

analyse -> build prompt -> call the LLM -> validate -> (repair) -> return.

Every exit from this function is safe to show a user. An answer that fails
the checks goes back to the model with what failed, and if it still fails,
only its parts that pass on their own are kept (validator.salvage_response).
If the LLM is unreachable or nothing survives, the caller gets templated
output built from extractor spans with `degraded: true` - never an
exception, and never unvalidated model text.
"""
from __future__ import annotations

import time
from typing import Any

from .analysis import analyse
from .crosscheck import compare
from .config import PipelineConfig, load
from .llm import LLMError, complete
from .prompt import build, repair_note
from .validator import salvage_response, templated_output, validate_response


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
    prompt = build(analysis, mode, config)
    started = time.monotonic()

    try:
        result = complete(prompt, config.llm, caller=llm)
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
    answers, attempts = [result.data], result.attempts
    last_call = time.monotonic() - started

    # A failed check is specific - "five" is a number the message never
    # gives - so the model is shown its answer and what failed, and asked
    # again. On the gold set the failures left were exactly this kind of
    # thing: counting the questions ("two"), a day the message never named
    # ("the next day"), a product it only implied ("Android"). 10 of 120
    # answers failed, and 7 passed in full once shown why. Bounded by count
    # and by time, so a repair cannot be what pushes the request past the
    # API's timeout.
    while (validated.get("degraded")
           and len(answers) <= config.repair_attempts
           and time.monotonic() - started + last_call <= config.repair_budget_seconds):
        call_started = time.monotonic()
        try:
            result = complete(
                prompt + repair_note(result.data, validated["degraded_reason"]),
                config.llm, caller=llm)
        except LLMError:
            break
        last_call = time.monotonic() - call_started
        answers.append(result.data)
        attempts += result.attempts
        validated = validate_response(result.data, message, analysis)

    # Still failing: keep what passes on its own, newest answer first, since
    # each repair was told what the one before got wrong.
    if validated.get("degraded"):
        for answer in reversed(answers):
            salvaged = salvage_response(answer, message)
            if salvaged is not None:
                validated = salvaged
                break

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
        "llm_attempts": attempts,
        "repairs": len(answers) - 1,
        "model": result.model,
        "model_comments_included": config.include_model_comments,
        "extracted_spans_in_prompt": config.include_extracted_spans,
    }
