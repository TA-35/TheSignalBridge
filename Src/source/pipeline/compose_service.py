"""Compose, served: classifier signals, the rewrite model, the grounding check.

The page asks in two stages (docs/api-contract.md, POST /api/compose):

    signals(message)   the three classifiers only. Milliseconds once warm.
    compose(message)   signals -> compose prompt -> llama-server -> grounding.

The rewrite model runs in llama-server on this host, with thinking off:

    llama-server -m <model>.gguf --jinja \\
        --chat-template-kwargs '{"enable_thinking":false}' --host 127.0.0.1 --port 8080

Settings come from the environment (or the .env files config.py loads):

    COMPOSE_LLM_URL      where llama-server listens. Unset means Compose is off:
                         /compose answers degraded, /compose/quick still works.
    COMPOSE_FEW_SHOT     1 for the untrained baseline, which needs the examples.
                         Leave unset for the fine-tuned model.
    COMPOSE_MODEL_NAME   reported back as `model`.
    COMPOSE_LLM_TIMEOUT  seconds per model call (default 45).

Or, on a host too small for the models, hand Compose to another copy of this
service that has them - in our deployment the uni GPU server:

    COMPOSE_REMOTE_URL     that service. /compose and /compose/quick are
                           forwarded there unchanged and nothing loads here.
    COMPOSE_REMOTE_TIMEOUT seconds to wait for it (default 25). Under the API's
                           gunicorn worker timeout (30s, three sync workers), so
                           a hung remote answers "degraded" here instead of
                           tying up the API's workers until they are killed.
    COMPOSE_REMOTE_TOKEN   sent as "Authorization: Bearer <token>"; the remote
                           service requires it when its PIPELINE_SERVICE_TOKEN
                           is set (service.py).

A rewrite is returned only if it passes the grounding check. If it fails, or
the reply isn't usable, the model is asked once more at a lower temperature;
if that fails too, the answer is rewrite = null with the failure classes. A
rewrite that dropped or invented a fact must never reach the page: it reads
as finished text and would be pasted into an email.

Never logs or stores message text.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from typing import Any, Iterable

from Src.source.pipeline import compose_client, compose_prompt as cp, grounding
from Src.source.pipeline.adapters import circa, politeness, tone

# The longest training message was ~1,500 characters. Much past 2,000 the
# reply (meaning + rewrite + notes) outgrows compose_client.MAX_TOKENS and
# arrives cut off. Kept in sync with backend/app/routes/compose.py and
# frontend/src/services/composeService.ts.
MAX_MESSAGE_CHARS = 2000

# First try, then the one retry. Lower is closer to the source text.
TEMPERATURES = (compose_client.DEFAULT_TEMPERATURE, 0.1)

# degraded_reason classes. The first three mean the grounding check rejected
# a rewrite; the page words those differently from "no rewrite came back".
NOT_CONFIGURED = "not_configured"
MODEL_UNAVAILABLE = "model_unavailable"
INVALID_OUTPUT = "invalid_output"

EMPTY_MEANING = {"ask": "", "deadline": "", "urgency": "", "tone": "", "implied": ""}


def settings() -> dict[str, Any]:
    few_shot = os.environ.get("COMPOSE_FEW_SHOT", "").strip() == "1"
    return {
        "url": os.environ.get("COMPOSE_LLM_URL", "").strip(),
        "few_shot": few_shot,
        "model": (os.environ.get("COMPOSE_MODEL_NAME", "").strip()
                  or ("qwen3.5-4b-baseline" if few_shot else "qwen3.5-4b-ft")),
        "timeout": float(os.environ.get("COMPOSE_LLM_TIMEOUT", "45")),
        "remote": os.environ.get("COMPOSE_REMOTE_URL", "").strip(),
        "remote_timeout": float(os.environ.get("COMPOSE_REMOTE_TIMEOUT", "25")),
        "remote_token": os.environ.get("COMPOSE_REMOTE_TOKEN", "").strip(),
    }


def _remote(base: str, path: str, message: str, timeout: float, token: str = "") -> dict[str, Any]:
    """POST the message to the remote Compose service. Raises on any failure."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base.rstrip("/") + path, data=json.dumps({"message": message}).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def signals(message: str) -> list[dict[str, Any]]:
    """The three classifiers in the contract shape. The adapters never raise:
    a failed one comes back as label "unknown", confidence 0.0."""
    conf = settings()
    if conf["remote"]:
        try:
            return _remote(conf["remote"], "/compose/quick", message, 5.0, conf["remote_token"])["signals"]
        except Exception:  # noqa: BLE001 - stage one is only an early paint
            return []
    return cp.clean_signals([tone.predict(message), politeness.predict(message),
                             circa.predict(message)])


def degraded(reasons: Iterable[str], *, signals: list | None = None,
             model: str | None = None) -> dict[str, Any]:
    """No rewrite to show. Same keys as an answer, so the page has one shape."""
    out: dict[str, Any] = {"stage": "compose", "degraded": True, "degraded_reason": list(reasons),
                           "rewrite": None, "notes": [], "meaning": dict(EMPTY_MEANING)}
    if signals is not None:
        out["signals"] = signals
    if model:
        out["model"] = model
    return out


def compose(message: str) -> dict[str, Any]:
    conf = settings()
    if conf["remote"]:
        try:
            out = _remote(conf["remote"], "/compose", message, conf["remote_timeout"], conf["remote_token"])
        except Exception:  # noqa: BLE001 - unreachable, timed out or erroring
            return degraded([MODEL_UNAVAILABLE], model=conf["model"])
        if out.get("degraded"):
            out["rewrite"] = None       # never pass on a rewrite that wasn't verified
        return out

    sig = signals(message)
    if not conf["url"]:
        return degraded([NOT_CONFIGURED], signals=sig, model=conf["model"])

    reasons: list[str] = []
    for temperature in TEMPERATURES:
        try:
            out = compose_client.complete(message, sig, few_shot=conf["few_shot"], base_url=conf["url"],
                                          temperature=temperature, timeout=conf["timeout"])
        except compose_client.ComposeServerError:
            # Unreachable or erroring: a second call would only double the wait.
            return degraded([MODEL_UNAVAILABLE], signals=sig, model=conf["model"])
        except cp.ComposeOutputError:
            reasons = [INVALID_OUTPUT]
            continue
        if out["notes"] == [cp.ALREADY_CLEAR_NOTE]:
            # Nothing needed changing, so the answer is the sender's own words,
            # which have nothing to verify. The model's copy can still differ
            # (a typo fixed, a name "corrected"), and checking that copy could
            # withhold a message that was fine as written.
            return {"stage": "compose", "degraded": False, "degraded_reason": [],
                    "rewrite": message, "notes": out["notes"], "meaning": out["meaning"],
                    "signals": sig, "checks": {"entities_kept": True, "nothing_added": True,
                                               "no_contradiction": True},
                    "model": conf["model"]}
        check = grounding.check(message, out["rewrite"])
        if check.ok:
            return {"stage": "compose", "degraded": False, "degraded_reason": [],
                    "rewrite": out["rewrite"], "notes": out["notes"], "meaning": out["meaning"],
                    "signals": sig, "checks": check.checks(), "model": conf["model"]}
        reasons = list(check.reasons)
    return degraded(reasons, signals=sig, model=conf["model"])


def warm_up() -> None:
    """Load the classifiers and the grounding models before the first request.

    A failure here doesn't stop the service - Decode on the same process keeps
    working - but it is said out loud, because without the grounding models
    every rewrite is withheld.
    """
    signals("Could you send the report to the client by Friday?")
    try:
        grounding.warm_up()
    except Exception as exc:  # noqa: BLE001
        print(f"compose: grounding models did not load ({type(exc).__name__}); "
              f"every rewrite will be withheld until they do", file=sys.stderr)
