"""The LLM call, with the provider behind a seam.

Two transports, chosen by config:

    openai   - any OpenAI-compatible endpoint. This is the Kimi path:
               base_url https://api.moonshot.ai/v1, models kimi-k3,
               kimi-k2.6, kimi-k2.7-code. Also reaches NVIDIA, Groq, OpenAI
               itself or any local server speaking the same protocol.
    anthropic - the Anthropic Messages API.

Both request structured output against the same JSON schema, so the
validator sees an identical shape either way and nothing downstream knows
which model answered. That matters beyond tidiness: swapping providers is a
one-line config change, so "is Kimi better than Claude here?" becomes a
measurable question rather than an argument.

One retry on malformed JSON, per the brief. If a schema-constrained request
still comes back unparseable, that is a transport problem and the caller
degrades to templated output rather than retrying forever.

Model and endpoint come from config. Nothing here is hardcoded, and no
credential is read or held by this module - each SDK resolves its own from
the environment. Nothing logs prompts or responses; on failure only the
exception type is recorded, never the payload.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ._lazy import LazyDict
from .config import LLMConfig, load
# FIELDS via prompt, which already imports it - llm.py has no other reason
# to reach analysis.py, and that module pulls spaCy in with it.
from .prompt import FIELDS, RESPONSE_SCHEMA


class LLMError(RuntimeError):
    """The model could not be reached, or would not return usable JSON."""


# Schema enforcement is not uniform across endpoints. Measured on NVIDIA NIM:
# kimi-k3 honours strict json_schema exactly, while llama-3.2-11b wraps the
# same request's output in ```json fences and sometimes omits a required key.
# Stripping fences costs nothing and rescues a response that is otherwise
# perfectly good JSON, so it runs before parsing rather than burning the one
# retry on a formatting quirk.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _strip_fences(text: str) -> str:
    cleaned = _FENCE_RE.sub("", text.strip())
    # A model may also prefix prose before the object; take from the first
    # brace when the whole string does not parse as-is.
    if not cleaned.startswith("{"):
        brace = cleaned.find("{")
        if brace > -1:
            cleaned = cleaned[brace:]
    return cleaned.strip()


REQUIRED_KEYS = ("summary", "claims", "unstated", "missing")


def _coerce_shape(data: dict[str, Any]) -> dict[str, Any]:
    """Nudge a nearly-right response into the declared shape.

    Endpoints do not all enforce the schema they are given. llama-3.2-11b on
    NVIDIA ignores the `field` enum and, observed live, returned `summary` as
    a list of two sentences rather than a string - which the frontend would
    have rendered complete with brackets and quotes.

    Coerce rather than reject: a summary split across two sentences is a
    formatting difference, not a wrong answer, and discarding good claims over
    it would be the same mistake as failing a whole response for one
    unverifiable quote. Anything that cannot be coerced is left alone for the
    validator to judge.
    """
    summary = data.get("summary")
    if isinstance(summary, (list, tuple)):
        data["summary"] = " ".join(str(s).strip() for s in summary if str(s).strip())
    elif summary is not None and not isinstance(summary, str):
        data["summary"] = str(summary)

    for key in ("claims", "unstated", "missing"):
        value = data.get(key)
        if value is None:
            data[key] = []
        elif not isinstance(value, (list, tuple)):
            # A single item where a list was asked for.
            data[key] = [value]
        else:
            data[key] = list(value)

    # `unstated` is rendered as plain text; anything else would print as an
    # object in the UI.
    data["unstated"] = [str(u).strip() for u in data["unstated"] if str(u).strip()]

    # `missing` drives checkboxes keyed by field, so an entry without a usable
    # field is not a gap the UI can render - it is a row with no identity. Drop
    # those rather than pass them on, and ignore any field outside our six: the
    # enum is advisory on endpoints that do not enforce it, and llama is
    # already known to invent field names.
    data["missing"] = [
        {"field": entry["field"], "question": str(entry.get("question", "")).strip()}
        for entry in data["missing"]
        if isinstance(entry, Mapping)
        and entry.get("field") in FIELDS
        and str(entry.get("question", "")).strip()
    ]
    return data


@dataclass
class LLMResult:
    """A parsed response, plus how much work it took to get it."""

    data: dict[str, Any]
    attempts: int
    model: str
    provider: str


# Clients are built once per kind even when several worker threads make their
# first call simultaneously. The factory is passed at the call site because it
# closes over the config.
_clients: LazyDict[Any] = LazyDict()


def reset_client() -> None:
    """Drop cached clients. For tests and for config changes at runtime."""
    _clients.reset()


# --------------------------------------------------------------------------
# OpenAI-compatible transport (Kimi / Moonshot, OpenAI, local servers)
# --------------------------------------------------------------------------

def _openai_client(config: LLMConfig) -> Any:
    def build(_key: str) -> Any:
        from openai import OpenAI  # noqa: E402 - lazy, tests need no SDK

        kwargs: dict[str, Any] = {
            "timeout": config.timeout_seconds,
            "max_retries": config.max_retries,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        # `is not None`: an empty key is a deliberate "no key" (see
        # config._api_key) and must not let the SDK find one of its own.
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return OpenAI(**kwargs)

    return _clients.get("openai", build)


def _call_openai(prompt: str, config: LLMConfig) -> str:
    """One OpenAI-compatible completion, constrained to the schema.

    No thinking parameter is sent, and a reasoning effort only when one is
    configured. kimi-k3 reasons unconditionally and has no field for it, so
    anything we passed would be ignored or rejected; GPT-OSS on Groq takes
    `reasoning_effort`, and at "low" answers in about a second.

    Streaming is on by default. A reasoning model asked for thousands of
    tokens of JSON can spend minutes before the first byte, and a
    non-streaming request just sits on an open socket until something in the
    chain times out. Streaming keeps the connection fed and lets the caller
    see progress; the text is reassembled here, so callers are unaffected.
    """
    client = _openai_client(config)
    request: dict[str, Any] = {
        "model": config.model,
        "max_tokens": config.max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if config.response_format == "json_schema":
        request["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "message_reading",
                "schema": RESPONSE_SCHEMA,
                "strict": True,
            },
        }
    elif config.response_format == "json_object":
        # Weaker: the endpoint guarantees valid JSON but not the shape.
        # The validator still rejects anything that does not fit.
        request["response_format"] = {"type": "json_object"}
    if config.reasoning_effort:
        request["reasoning_effort"] = config.reasoning_effort

    if not config.stream:
        response = client.chat.completions.create(**request)
        choices = getattr(response, "choices", None) or []
        if not choices:
            raise LLMError("response contained no choices")
        content = getattr(choices[0].message, "content", None)
        if not content:
            raise LLMError("response contained no content")
        return content

    pieces: list[str] = []
    for chunk in client.chat.completions.create(**request, stream=True):
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        piece = getattr(choices[0].delta, "content", None)
        if piece:
            pieces.append(piece)
    text = "".join(pieces)
    if not text:
        raise LLMError("stream produced no content")
    return text


# --------------------------------------------------------------------------
# Anthropic transport
# --------------------------------------------------------------------------

def _anthropic_client(config: LLMConfig) -> Any:
    def build(_key: str) -> Any:
        import anthropic  # noqa: E402 - lazy

        kwargs: dict[str, Any] = {
            "timeout": config.timeout_seconds,
            "max_retries": config.max_retries,
        }
        if config.base_url:
            kwargs["base_url"] = config.base_url
        if config.api_key:
            kwargs["api_key"] = config.api_key
        return anthropic.Anthropic(**kwargs)

    return _clients.get("anthropic", build)


def _call_anthropic(prompt: str, config: LLMConfig) -> str:
    client = _anthropic_client(config)
    response = client.messages.create(
        model=config.model,
        max_tokens=config.max_tokens,
        messages=[{"role": "user", "content": prompt}],
        thinking={"type": "adaptive"},
        output_config={
            "effort": config.effort,
            "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA},
        },
    )
    # A refusal is a 200 with no usable content - check before reading blocks.
    if getattr(response, "stop_reason", None) == "refusal":
        raise LLMError("model declined the request")
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
    raise LLMError("response contained no text block")


TRANSPORTS: dict[str, Callable[[str, LLMConfig], str]] = {
    "openai": _call_openai,
    "nvidia": _call_openai,  # same protocol, different endpoint and key
    "groq": _call_openai,
    "anthropic": _call_anthropic,
}

# A wrong key, a refused key or a wrong model id fails the same way every
# time; sending it again only adds a round trip before the same answer.
_NOT_WORTH_RETRYING = frozenset({401, 403, 404})


def _send(
    send: Callable[[str, LLMConfig], str], prompt: str, config: LLMConfig
) -> tuple[str, int]:
    """One request, sent again on a failure that may not recur. Returns the
    raw text and how many retries it took."""
    retries = 0
    while True:
        try:
            return send(prompt, config), retries
        except Exception as exc:  # noqa: BLE001 - re-raised once out of retries
            if (retries >= config.transport_retries
                    or getattr(exc, "status_code", None) in _NOT_WORTH_RETRYING):
                raise
            retries += 1


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def complete(
    prompt: str,
    config: LLMConfig | None = None,
    caller: Callable[[str, LLMConfig], str] | None = None,
) -> LLMResult:
    """Send `prompt`, return parsed JSON. Retries once on malformed JSON, and
    once on a failed request (config.transport_retries).

    `caller` substitutes the transport, so tests never touch a live endpoint.
    """
    config = config or load().llm

    if caller is not None:
        send = caller
    else:
        try:
            send = TRANSPORTS[config.provider]
        except KeyError:
            raise LLMError(
                f"unknown provider {config.provider!r}; "
                f"expected one of {sorted(TRANSPORTS)}"
            ) from None

    attempts = 0
    last_error: Exception | None = None
    for _ in range(config.json_retries + 1):
        attempts += 1
        try:
            raw, retries = _send(send, prompt, config)
        except LLMError:
            raise
        except Exception as exc:  # noqa: BLE001 - transport failure
            # Never include the prompt or the response in the message.
            raise LLMError(f"request failed: {type(exc).__name__}") from exc
        attempts += retries

        try:
            data = json.loads(_strip_fences(raw))
        except (json.JSONDecodeError, TypeError) as exc:
            last_error = exc
            continue

        if not isinstance(data, dict):
            last_error = TypeError("response JSON was not an object")
            continue

        # A schema-constrained request should make this impossible, but not
        # every endpoint enforces the schema it was given. Fill rather than
        # reject: the validator still checks every span and entity, and a
        # missing `summary` is not a reason to throw away good claims.
        missing = [k for k in REQUIRED_KEYS if k not in data]
        if missing:
            data = {**{"summary": "", "claims": [], "unstated": [],
                       "missing": []}, **data}
        data = _coerce_shape(data)

        return LLMResult(data=data, attempts=attempts,
                         model=config.model, provider=config.provider)

    raise LLMError(
        f"no parseable JSON after {attempts} attempt(s): "
        f"{type(last_error).__name__ if last_error else 'unknown'}"
    )
