"""POST /api/review - the LLM-backed reading, proxied to the inference service.

This is additive. /api/decode is untouched: same URL, same shape, same ~50ms,
same code path. Nothing already working changes.

The heavy lifting happens in a separate process (Src/source/pipeline/service.py)
because it holds ~505MB of models and this box is a t3.micro running three
gunicorn workers. This module only forwards the request and normalises the
failure modes.

Deliberately stdlib-only. Adding `requests` here would mean a new entry in
backend/requirements.txt, a new package on a 1GB box, and a changed dependency
set in a CI/CD pipeline that currently works - all to do what urllib already
does. The API's dependency list is unchanged by this feature.

If the inference service is unreachable, slow, or broken, this returns 200
with `degraded: true` rather than an error. A reader who pasted a message
should get the extractor's reading, not a stack trace - and the frontend has
one response shape to render either way.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from flask import Blueprint, current_app, jsonify, request

bp = Blueprint("review", __name__)

# Kept in sync with MAX_MESSAGE_LENGTH in routes/decode.py and with
# PIPELINE_MAX_MESSAGE_CHARS in the pipeline. All three guard the same thing;
# the pipeline guards itself because it is reachable without passing here.
MAX_MESSAGE_LENGTH = 5000


def _degraded(reason: str, status: int = 200):
    """The shape the frontend renders when the model could not be consulted.

    200, not 5xx: the request succeeded, the answer is just reduced. A 5xx
    would make the frontend show an error page for something it can render.
    """
    return jsonify({
        "stage": "review",
        "degraded": True,
        "degraded_reason": [reason],
        "summary": "",
        "claims": [],
        "missing": [],
        "unstated": [],
    }), status


def _call_service(path: str, payload: dict, timeout: float):
    """POST JSON to the inference service. Raises urllib errors to the caller."""
    base = current_app.config.get("INFERENCE_URL", "").rstrip("/")
    if not base:
        raise RuntimeError("INFERENCE_URL is not configured")

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{base}{path}", data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8")), response.status


def _proxy(path: str, timeout_key: str, default_timeout: float):
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")

    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "Please enter a message"}), 400
    if len(message) > MAX_MESSAGE_LENGTH:
        return (
            jsonify({"error": f"Message is too long (limit is "
                              f"{MAX_MESSAGE_LENGTH} characters)."}),
            413,
        )

    if not current_app.config.get("INFERENCE_URL", "").strip():
        # A deploy that has not been given INFERENCE_URL is a configuration
        # state, not a runtime fault. Say so plainly rather than surfacing a
        # RuntimeError, which reads like a crash and sends whoever is on call
        # looking for the wrong thing.
        return _degraded("inference service not configured (INFERENCE_URL unset)")

    payload = {"message": message}
    if "mode" in data:
        payload["mode"] = data["mode"]

    timeout = float(current_app.config.get(timeout_key, default_timeout))
    try:
        result, status = _call_service(path, payload, timeout)
    except urllib.error.HTTPError as exc:
        # The service answered with an error - pass 4xx through so a too-long
        # or empty message keeps its meaning, but never leak a 5xx body.
        if 400 <= exc.code < 500:
            try:
                return jsonify(json.loads(exc.read().decode("utf-8"))), exc.code
            except Exception:  # noqa: BLE001
                return jsonify({"error": "Invalid request."}), exc.code
        return _degraded(f"inference service error {exc.code}")
    except urllib.error.URLError as exc:
        return _degraded(f"inference service unreachable: "
                         f"{type(exc.reason).__name__}")
    except TimeoutError:
        return _degraded("inference service timed out")
    except Exception as exc:  # noqa: BLE001 - never 500 on the user
        return _degraded(f"inference call failed: {type(exc).__name__}")

    return jsonify(result), status


@bp.post("/quick")
def review_quick():
    """Stage one: extractor only, no model call. Milliseconds.

    The frontend renders this immediately so the user never sees an empty
    screen, then replaces it with the full reading when that arrives.
    """
    return _proxy("/analyse", "INFERENCE_QUICK_TIMEOUT", 5.0)


@bp.post("")
def review_full():
    """Stage two: the full pipeline including the LLM. Seconds."""
    return _proxy("/review", "INFERENCE_TIMEOUT", 30.0)


@bp.get("/health")
def review_health():
    """Whether the inference service is reachable from this box.

    Useful in deployment: a 200 here with "reachable": false means the API is
    fine and the inference service is not, which is a different fix from the
    API being down.
    """
    base = current_app.config.get("INFERENCE_URL", "").rstrip("/")
    if not base:
        return jsonify({"reachable": False, "reason": "INFERENCE_URL not set"}), 200
    try:
        with urllib.request.urlopen(f"{base}/health", timeout=3.0) as response:
            return jsonify({"reachable": True,
                            "inference": json.loads(response.read().decode())}), 200
    except Exception as exc:  # noqa: BLE001
        return jsonify({"reachable": False,
                        "reason": type(exc).__name__}), 200
