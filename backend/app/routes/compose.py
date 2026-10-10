"""POST /api/compose - the rewrite, proxied to the inference service.

Same arrangement as routes/review.py: the models live in a separate process
(Src/source/pipeline/service.py, see compose_service.py there) and this module
only forwards the request and normalises the failure modes. Stdlib-only, for
the same reasons review.py gives.

Any failure answers 200 with `degraded: true` and `rewrite: null` - the shape
docs/api-contract.md defines - so the page always has one thing to render.
A degraded answer never carries a rewrite: the service already withholds one
that failed the grounding check, and this drops any that slips through.
"""
from __future__ import annotations

import json
import urllib.error

from flask import Blueprint, current_app, jsonify, request

from ..limiter import limiter
from .review import CHEAP_LIMITS, MODEL_CALL_LIMITS, _call_service

bp = Blueprint("compose", __name__)

# Lower than Decode's 5000: the model was trained on messages up to ~1,500
# characters, and much past 2,000 its reply outgrows its token budget. Kept in
# sync with MAX_MESSAGE_CHARS in Src/source/pipeline/compose_service.py and
# MAX_MESSAGE_LENGTH in frontend/src/services/composeService.ts.
MAX_MESSAGE_LENGTH = 2000

EMPTY_MEANING = {"ask": "", "deadline": "", "urgency": "", "tone": "", "implied": ""}


def _degraded(reason: str):
    return jsonify({
        "stage": "compose",
        "degraded": True,
        "degraded_reason": [reason],
        "rewrite": None,
        "notes": [],
        "meaning": dict(EMPTY_MEANING),
    }), 200


def _message():
    """The message, or the 400/413 answer for it."""
    message = (request.get_json(silent=True) or {}).get("message", "")
    if not isinstance(message, str) or not message.strip():
        return None, (jsonify({"error": "Please enter a message"}), 400)
    if len(message) > MAX_MESSAGE_LENGTH:
        return None, (jsonify({"error": f"Message is too long (limit is "
                                        f"{MAX_MESSAGE_LENGTH} characters)."}), 413)
    return message, None


def _forward(path: str, message: str, timeout: float):
    """(result, status) from the service, or a degraded answer for any failure."""
    if not current_app.config.get("INFERENCE_URL", "").strip():
        return None, _degraded("inference service not configured (INFERENCE_URL unset)")
    try:
        return _call_service(path, {"message": message}, timeout), None
    except urllib.error.HTTPError as exc:
        # Pass a 4xx through so a too-long or empty message keeps its meaning,
        # but never leak a 5xx body.
        if 400 <= exc.code < 500:
            try:
                return None, (jsonify(json.loads(exc.read().decode("utf-8"))), exc.code)
            except Exception:  # noqa: BLE001
                return None, (jsonify({"error": "Invalid request."}), exc.code)
        return None, _degraded(f"inference service error {exc.code}")
    except urllib.error.URLError as exc:
        return None, _degraded(f"inference service unreachable: {type(exc.reason).__name__}")
    except TimeoutError:
        return None, _degraded("inference service timed out")
    except Exception as exc:  # noqa: BLE001 - never 500 on the user
        return None, _degraded(f"inference call failed: {type(exc).__name__}")


@bp.post("/quick")
@limiter.limit(CHEAP_LIMITS)
def compose_quick():
    """Stage one: the classifier signals, no model call. Milliseconds."""
    message, error = _message()
    if error:
        return error
    answer, failed = _forward("/compose/quick", message,
                              float(current_app.config.get("INFERENCE_QUICK_TIMEOUT", 5.0)))
    if failed:
        # Stage one is only an early paint; without it the page waits for
        # stage two, which carries the signals too.
        return jsonify({"stage": "analyse", "signals": []}), 200
    result, status = answer
    return jsonify(result), status


@bp.post("")
@limiter.limit(MODEL_CALL_LIMITS)
def compose_full():
    """Stage two: the rewrite, grounding-checked. Seconds."""
    message, error = _message()
    if error:
        return error
    answer, failed = _forward("/compose", message,
                              float(current_app.config.get("COMPOSE_TIMEOUT", 100.0)))
    if failed:
        return failed
    result, status = answer
    if isinstance(result, dict) and result.get("degraded"):
        result["rewrite"] = None
    return jsonify(result), status
