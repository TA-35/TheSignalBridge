"""The pipeline as a standalone HTTP service.

Why separate from the Flask API rather than imported into it: measured, the
pipeline holds ~505MB resident once spaCy, scikit-learn and both model
bundles are loaded. The API box is a t3.micro (1024MB) running three gunicorn
workers, so importing this into the API would need 1435MB and would not fit.
Dropping the API to one worker to make room would serialise every request,
including the 50ms /api/decode calls, behind a 9-second LLM call.

So this runs as its own process - one worker, its own host or container -
and backend/app/routes/review.py reaches it over HTTP. The API keeps its
three fast workers, its existing deploy, and its dependency list unchanged.

Two endpoints, because the frontend renders in two stages:

    POST /analyse   the local path only. ~6ms. Extractor spans, message type,
                    what is missing, and the three model comments. No LLM, so
                    no network call and no token spend.
    POST /review    the full pipeline including the LLM. 5-9s.

    GET  /health    liveness plus which model is configured.

Run it:
    python -m Src.source.pipeline.service                 # dev
    gunicorn --workers 1 --bind 127.0.0.1:8100 \\
        'Src.source.pipeline.service:create_service()'    # production

One worker on purpose. The models are loaded per process, so a second worker
doubles the memory for no throughput gain - the LLM call is the bottleneck
and it is I/O, not CPU.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from flask import Flask, jsonify, request  # noqa: E402

from Src.source.pipeline.analysis import analyse  # noqa: E402
from Src.source.pipeline.config import load  # noqa: E402
from Src.source.pipeline.pipeline import run  # noqa: E402

SERVICE_VERSION = "1"


def _message_from(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    value = payload.get("message", "")
    return value if isinstance(value, str) else ""


def _warm_up() -> None:
    """Load every model before the first request arrives.

    Measured: the first /analyse took 1648ms and every one after it took 6ms.
    That gap is spaCy and the two model bundles loading lazily, and without
    this the cost lands on whichever user happens to arrive first after a
    deploy or restart. Doing it at startup moves it to a moment nobody is
    waiting on - and it makes a failed model load surface immediately, rather
    than as a mysterious first-request stall.
    """
    try:
        analyse("Could you send the report to the client by Friday?")
    except Exception:  # noqa: BLE001 - a warm-up failure must not stop boot
        # The adapters already degrade to their unavailable stubs, so the
        # service still serves; it just pays the load cost on first use.
        pass


def create_service(warm: bool = True) -> Flask:
    app = Flask(__name__)
    if warm:
        _warm_up()

    @app.get("/health")
    def health():
        """Liveness, and enough config to diagnose a misrouted request.

        No secret is echoed - only whether a key resolved at all.
        """
        config = load()
        return jsonify({
            "status": "ok",
            "version": SERVICE_VERSION,
            "provider": config.llm.provider,
            "model": config.llm.model,
            "has_credentials": bool(config.llm.api_key),
            "max_message_chars": config.max_message_chars,
        })

    @app.post("/analyse")
    def analyse_endpoint():
        """Stage one: everything that does not need the model. ~6ms."""
        config = load()
        message = _message_from(request.get_json(silent=True))
        if not message.strip():
            return jsonify({"error": "Please enter a message"}), 400
        if len(message) > config.max_message_chars:
            return jsonify({
                "error": f"Message is too long (limit is "
                         f"{config.max_message_chars} characters)."
            }), 413

        result = analyse(message)
        return jsonify({
            "stage": "analyse",
            "message_type": result.message_type,
            "extraction": result.extraction.as_dict(),
            "comments": result.comments,
        })

    @app.post("/review")
    def review_endpoint():
        """Stage two: the full pipeline, including the LLM call.

        Never raises past this point - run() degrades rather than throwing,
        and anything unexpected still returns the degraded shape so the
        caller has one contract to handle.
        """
        config = load()
        message = _message_from(request.get_json(silent=True))
        if not message.strip():
            return jsonify({"error": "Please enter a message"}), 400
        if len(message) > config.max_message_chars:
            return jsonify({
                "error": f"Message is too long (limit is "
                         f"{config.max_message_chars} characters)."
            }), 413

        mode = (request.get_json(silent=True) or {}).get("mode", "review")
        if mode not in {"review", "form"}:
            return jsonify({"error": "mode must be 'review' or 'form'"}), 400

        try:
            result = run(message, mode, config)
        except Exception as exc:  # noqa: BLE001 - the service must not 500
            # Name the failure class, never the message body.
            return jsonify({
                "stage": "review",
                "degraded": True,
                "degraded_reason": [f"pipeline error: {type(exc).__name__}"],
                "claims": [], "missing": [], "summary": "",
            }), 200

        return jsonify({"stage": "review", **result})

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PIPELINE_SERVICE_PORT", "8100"))
    create_service().run(host="127.0.0.1", port=port, threaded=True)
