"""Pipeline configuration. Everything environment-driven, nothing hardcoded.

The model id and endpoint in particular must be settable without a code
change - a deployment that needs a different model, or a proxy in front of
the API, should be an env var, not a pull request.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Load .env before any dataclass default is evaluated, so a key placed in a
# file is picked up the same as one exported in the shell. Without this the
# pipeline reads only the process environment, and a key sitting in .env does
# nothing at all - silently, which is the worst way for it to fail.
#
# Never overrides an already-set variable: an explicit `export` wins over the
# file, which is what you want when overriding a single value for one run.
_REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_env_files() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # dotenv is optional; the shell still works
        return
    for candidate in (
        _REPO_ROOT / ".env",
        _REPO_ROOT / "backend" / ".env",
        Path(__file__).resolve().parent / ".env",
    ):
        if candidate.is_file():
            load_dotenv(candidate, override=False)


_load_env_files()


def _number(name: str, default: str, cast):
    """Read a numeric setting, falling back to the default if it is malformed.

    A single stray character crashed the whole config: PIPELINE_LLM_TIMEOUT
    was typed as "900v" and float() raised, taking down 46 tests and - had it
    happened in the inference host's .env - the service itself, with a
    ValueError that says nothing about which variable is at fault.

    Configuration should degrade, not explode. A bad value is reported on
    stderr, names the variable, and the documented default is used instead.
    """
    raw = os.environ.get(name, default)
    try:
        return cast(raw)
    except (TypeError, ValueError):
        print(f"warning: {name}={raw!r} is not a valid number; "
              f"using the default {default!r}", file=sys.stderr)
        return cast(default)


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Per-provider defaults, so switching provider does not also require
# remembering a model id and a base URL. Any of them can still be overridden
# individually.
PROVIDER_DEFAULTS: dict[str, dict[str, str | None]] = {
    # Kimi direct from Moonshot. Keys look like "sk-...".
    # Models: kimi-k3 (reasoning), kimi-k2.6, kimi-k2.7-code.
    "openai": {
        "model": "kimi-k3",
        "base_url": "https://api.moonshot.ai/v1",
        "key_env": "MOONSHOT_API_KEY",
    },
    # Kimi hosted on NVIDIA NIM. Same OpenAI-compatible protocol, different
    # endpoint, different key format ("nvapi-...") and vendor-prefixed model
    # ids. A Moonshot key sent here - or an NVIDIA key sent to Moonshot -
    # fails with AuthenticationError, which is easy to misread as a bad key
    # rather than a wrong endpoint.
    "nvidia": {
        "model": "moonshotai/kimi-k3",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_env": "NVIDIA_API_KEY",
    },
    "anthropic": {
        "model": "claude-opus-5",
        "base_url": None,
        "key_env": "ANTHROPIC_API_KEY",
    },
}

def _provider() -> str:
    return os.environ.get("PIPELINE_LLM_PROVIDER", "openai")


# Kept as a module attribute for callers that want the value without
# constructing a config, but resolved through _provider() everywhere inside
# this module so a runtime change is honoured.
DEFAULT_PROVIDER = _provider()


def _provider_default(key: str) -> str | None:
    return PROVIDER_DEFAULTS.get(_provider(), {}).get(key)


# Providers that speak the OpenAI protocol, whatever their branding.
OPENAI_COMPATIBLE = frozenset({"openai", "nvidia"})


def _api_key() -> str | None:
    """The key for the selected provider, if it is under a provider-specific
    name. Returning None lets the SDK resolve its own, which is the better
    path - it also picks up OPENAI_API_KEY, profiles and so on."""
    env = _provider_default("key_env")
    if env and os.environ.get(env):
        return os.environ[env]
    # A key under another provider's variable name is a common mix-up worth
    # tolerating: what matters is that the key reaches the right endpoint.
    for fallback in ("NVIDIA_API_KEY", "MOONSHOT_API_KEY", "OPENAI_API_KEY"):
        if os.environ.get(fallback):
            return os.environ[fallback]
    return None


@dataclass(frozen=True)
class LLMConfig:
    """How to reach the model.

    No secret is stored here beyond a reference: `api_key` is only populated
    when the key lives under a provider-specific variable the SDK would not
    find on its own (MOONSHOT_API_KEY, say). Otherwise it stays None and each
    SDK resolves its own credential from the environment.
    """

    # Every field uses default_factory, not a plain default. A dataclass
    # evaluates a plain default ONCE, when the class is created - so
    # `model: str = os.environ.get(...)` reads the environment at import and
    # never again, and load()'s promise to re-read it would be false.
    # Measured: setting PIPELINE_LLM_MODEL after import had no effect at all.
    provider: str = field(default_factory=_provider)
    model: str = field(default_factory=lambda: (
        os.environ.get("PIPELINE_LLM_MODEL")
        or _provider_default("model") or "kimi-k3"))
    # None means "the SDK's default endpoint".
    base_url: str | None = field(default_factory=lambda: (
        os.environ.get("PIPELINE_LLM_BASE_URL") or _provider_default("base_url")))
    api_key: str | None = field(default_factory=_api_key)
    max_tokens: int = field(
        default_factory=lambda: _number("PIPELINE_LLM_MAX_TOKENS", "8000", int))
    # low | medium | high | xhigh | max. This is a bounded extraction job over
    # a short message, not open-ended reasoning, so the default is deliberately
    # below the API's own default of high.
    effort: str = field(
        default_factory=lambda: os.environ.get("PIPELINE_LLM_EFFORT", "medium"))
    timeout_seconds: float = field(
        default_factory=lambda: _number("PIPELINE_LLM_TIMEOUT", "600", float))

    # SDK-level retries on 5xx/429, separate from json_retries. The SDKs
    # default to 2, which multiplies against the timeout: 900s x 3 attempts
    # is 45 minutes on a single failing call. A real run measured 911s on one
    # NVIDIA InternalServerError - that was a retry chain, not a slow model.
    # One retry is enough to ride out a blip without stalling a whole sweep.
    max_retries: int = field(
        default_factory=lambda: _number("PIPELINE_LLM_MAX_RETRIES", "1", int))
    # One retry on malformed JSON, per the brief.
    json_retries: int = field(
        default_factory=lambda: _number("PIPELINE_LLM_JSON_RETRIES", "1", int))

    # Stream the response. On by default: a reasoning model can take minutes
    # to first byte, and a non-streaming request just holds an open socket
    # until something times out.
    stream: bool = field(default_factory=lambda: _flag("PIPELINE_LLM_STREAM", True))

    # json_schema | json_object | none. Not every OpenAI-compatible endpoint
    # implements strict schemas, so this can be stepped down without a code
    # change - the validator rejects a wrong shape either way.
    response_format: str = field(default_factory=lambda: os.environ.get(
        "PIPELINE_LLM_RESPONSE_FORMAT", "json_schema"))


@dataclass(frozen=True)
class PipelineConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)

    # The A/B switch. Turning this off drops all three model comments from the
    # prompt while leaving the extractor spans in place, so the same examples
    # can be run both ways and compared. Flip it with the environment variable
    # or `run_examples.py --no-model-comments`; no code edit either way.
    include_model_comments: bool = field(
        default_factory=lambda: _flag("PIPELINE_INCLUDE_MODEL_COMMENTS", True))

    # Comments at or below this confidence are omitted entirely rather than
    # shown to the model as noise. 0.0 is the unavailable stub.
    min_comment_confidence: float = field(default_factory=lambda: float(
        os.environ.get("PIPELINE_MIN_COMMENT_CONFIDENCE", "0.01")))

    # The second experiment axis. True (default) is the original design: the
    # extractor's spans go into the prompt and the LLM works from them. False
    # is "LLM leads" - the extractor still runs every request, but only as an
    # independent cross-check, never as an input. Neither is obviously right,
    # which is why it is a flag and not a rewrite: the extractor has known
    # bugs, and the LLM has no measurements at all yet.
    include_extracted_spans: bool = field(
        default_factory=lambda: _flag("PIPELINE_INCLUDE_EXTRACTED_SPANS", True))

    # Longest message the pipeline will process. Matches MAX_MESSAGE_LENGTH in
    # backend/app/routes/decode.py, which guards the HTTP boundary - but the
    # pipeline guards itself too, because it is the component that spends
    # money: run_examples.py and any future caller reach it without passing
    # through Flask. Measured: a 111KB message builds a 295,569-character
    # prompt, roughly 74k tokens in a single request.
    #
    # Rejected, never truncated. Every span indexes into the original message,
    # so trimming the input would silently invalidate the traceability
    # guarantee this whole pipeline exists to provide.
    max_message_chars: int = field(default_factory=lambda: int(
        os.environ.get("PIPELINE_MAX_MESSAGE_CHARS", "5000")))


def load() -> PipelineConfig:
    """Read configuration fresh from the environment."""
    return PipelineConfig(llm=LLMConfig())
