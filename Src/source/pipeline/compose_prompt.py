"""The compose prompt - single source of truth for the rewrite format.

Every place that talks to the rewrite model builds its input here: teacher
generation of training data, the training script's formatting, the few-shot
baseline, eval, and serving. If any of them formats a message differently,
the fine-tuned model is evaluated and served on inputs it was never trained
on. So nothing outside this module assembles a compose prompt by hand.

There is one prompt and one output format for all of them: the teacher, the
baseline and the fine-tuned model all return {"meaning", "rewrite",
"notes"}. Working out the meaning first is part of the task, and the Compose
page shows it to the sender.

Wording lives in prompts/compose_system.txt and the few-shot examples in
prompts/compose_examples.json, so they can be edited and diffed without
touching Python. Any change to them changes `fingerprint()`; generated data
records the fingerprint it was made with, so a mismatch is detectable
instead of silent.

Standard library only. The training script imports this on the GPU box and
the data scripts import it on laptops, neither of which has the rest of the
pipeline installed - so nothing here imports from analysis, config or llm.

Separate from prompt.py, which builds the Decode (review/form) prompts and
has its own response schema.
"""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

PROMPT_VERSION = "compose-v2"

# Fixed order, so the same signals always render to the same bytes.
SIGNAL_ORDER = ("tone", "politeness", "circa")

ALREADY_CLEAR_NOTE = "Already clear, kept as written."

# What contract.unavailable() returns. Repeated here rather than imported to
# keep this module dependency-free; test_compose_prompt pins the two together.
_FAILED_LABEL = "unknown"

# Circa sources are stored as "Q: <question>\nReply: <reply>".
_CIRCA = re.compile(r"\AQ: (?P<question>.*?)\nReply: (?P<reply>.*)\Z", re.S)

MEANING_KEYS = ("ask", "deadline", "urgency", "tone", "implied")
URGENCY_LEVELS = ("low", "medium", "high")

# `meaning` comes first so the model works out what the message means before
# it rewrites it - decoding order is reasoning order for a model with
# thinking switched off.
RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "meaning": {
            "type": "object",
            "properties": {
                **{k: {"type": "string"} for k in MEANING_KEYS},
                "urgency": {"type": "string", "enum": list(URGENCY_LEVELS)},
            },
            "required": list(MEANING_KEYS),
            "additionalProperties": False,
        },
        "rewrite": {"type": "string", "minLength": 1},
        "notes": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "minItems": 1,
            "maxItems": 3,
        },
    },
    "required": ["meaning", "rewrite", "notes"],
    "additionalProperties": False,
}


class ComposeOutputError(ValueError):
    """The model's reply is not a usable {"meaning", "rewrite", "notes"} object."""


# --------------------------------------------------------------------------
# Files
# --------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _read(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8")


def system_prompt() -> str:
    return _read("compose_system.txt").rstrip("\n")


@lru_cache(maxsize=None)
def examples() -> tuple[dict[str, Any], ...]:
    return tuple(json.loads(_read("compose_examples.json")))


def fingerprint() -> str:
    """Short hash of everything that shapes the prompt.

    Record it with generated data and training runs; two artefacts with
    different fingerprints were made with different prompts.
    """
    parts = [
        PROMPT_VERSION,
        _read("compose_system.txt"),
        _read("compose_examples.json"),
    ]
    return hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()[:12]


# --------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------

def failed_signal(model: str) -> dict[str, Any]:
    """The shape of a classifier that could not run - same as production."""
    return {"model": model, "label": _FAILED_LABEL, "confidence": 0.0}


def _is_failed(signal: Mapping[str, Any]) -> bool:
    label = str(signal.get("label") or "").strip().lower()
    confidence = signal.get("confidence")
    # "unavailable" and None are what older data scripts wrote for a failure.
    return label in ("", _FAILED_LABEL, "unavailable") or not confidence


def clean_signals(signals: Iterable[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    """Exactly one signal per classifier, in SIGNAL_ORDER, with only the keys
    the model sees.

    Drops `note` (adapter-internal, not for the rewrite model). A missing or
    failed classifier becomes failed_signal(), so training data and serving
    present a failure identically.
    """
    by_model = {str(s.get("model")): s for s in (signals or []) if isinstance(s, Mapping)}
    out = []
    for name in SIGNAL_ORDER:
        s = by_model.get(name)
        if s is None or _is_failed(s):
            out.append(failed_signal(name))
        else:
            out.append({
                "model": name,
                "label": str(s["label"]),
                "confidence": round(float(s["confidence"]), 3),
            })
    return out


def _format_signals(signals: Iterable[Mapping[str, Any]] | None) -> str:
    return "\n".join(
        f"- {s['model']}: {s['label']} ({s['confidence']:.2f})"
        for s in clean_signals(signals)
    )


# --------------------------------------------------------------------------
# Messages
# --------------------------------------------------------------------------

def split_circa(source: str) -> tuple[str | None, str]:
    """(question, reply) for a Circa source, (None, source) for anything else."""
    m = _CIRCA.match(source)
    if not m:
        return None, source
    return m.group("question"), m.group("reply")


def user_prompt(source: str, signals: Iterable[Mapping[str, Any]] | None) -> str:
    question, message = split_circa(source)
    parts = [
        "Classifier signals (hints only):",
        _format_signals(signals),
        "",
    ]
    if question is not None:
        parts += [
            "The message is a reply to this question:",
            f"<question>\n{question}\n</question>",
            "",
        ]
    parts += [
        "Message or notes to rewrite:",
        f"<message>\n{message}\n</message>",
    ]
    return "\n".join(parts)


def assistant_response(record: Mapping[str, Any]) -> str:
    """The exact JSON text the model is trained to produce for `record`.

    Training targets go through here so they are byte-for-byte the format
    parse_response() reads back at serving time.
    """
    return json.dumps({
        "meaning": {k: record["meaning"][k] for k in MEANING_KEYS},
        "rewrite": record["rewrite"],
        "notes": list(record["notes"]),
    }, ensure_ascii=False)


def build_messages(
    source: str,
    signals: Iterable[Mapping[str, Any]] | None,
    *,
    few_shot: bool = False,
) -> list[dict[str, str]]:
    """Chat messages for one source message.

    few_shot=False  the fine-tuned model, in training and serving: the
                    examples are learned, not shown.
    few_shot=True   anything untrained - the teacher generating training
                    data and the baseline - which needs to see examples.
    """
    messages = [{"role": "system", "content": system_prompt()}]
    if few_shot:
        for ex in examples():
            messages.append({"role": "user", "content": user_prompt(ex["source"], ex["signals"])})
            messages.append({"role": "assistant", "content": assistant_response(ex)})
    messages.append({"role": "user", "content": user_prompt(source, signals)})
    return messages


# --------------------------------------------------------------------------
# Reading the reply
# --------------------------------------------------------------------------

def parse_response(text: str) -> dict[str, Any]:
    """Pull the JSON object out of a model reply and check its shape.

    Tolerates markdown fences and stray text around the object - small
    models add them even when told not to. Raises ComposeOutputError with a
    reason a reject log can use. Content checks (entities, note length,
    length ratio, NLI) are the filter's and the grounding check's job, not
    this function's.
    """
    cleaned = re.sub(r"```(?:json)?", "", str(text)).strip()
    match = re.search(r"\{.*\}", cleaned, re.S)
    if not match:
        raise ComposeOutputError("no JSON object in the reply")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ComposeOutputError(f"reply is not valid JSON ({exc.msg})") from None
    if not isinstance(data, dict):
        raise ComposeOutputError("reply is not a JSON object")

    rewrite = data.get("rewrite")
    if not isinstance(rewrite, str) or not rewrite.strip():
        raise ComposeOutputError("rewrite missing or empty")
    notes = data.get("notes")
    if not isinstance(notes, list) or not all(isinstance(n, str) and n.strip() for n in notes):
        raise ComposeOutputError("notes missing, not a list, or contains an empty note")
    if not 1 <= len(notes) <= 3:
        raise ComposeOutputError(f"{len(notes)} notes (need 1-3)")

    meaning = data.get("meaning")
    if not isinstance(meaning, dict) or any(k not in meaning for k in MEANING_KEYS):
        raise ComposeOutputError("meaning missing or incomplete")
    if meaning["urgency"] not in URGENCY_LEVELS:
        raise ComposeOutputError(f"urgency {meaning['urgency']!r} is not low/medium/high")

    return {
        "meaning": {k: str(meaning[k]).strip() for k in MEANING_KEYS},
        "rewrite": rewrite.strip(),
        "notes": [n.strip() for n in notes],
    }
