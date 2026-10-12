"""POST /api/compose/feedback and GET /api/compose/feedback/summary - 👍/👎 on a rewrite.

A rating takes exactly five fields and anything else is refused, so a message
or a rewrite can't reach the database by accident or from a client that sends
more than it was asked for. The privacy page promises messages are never
stored, and this keeps that true. Signed in or not makes no difference, and
nothing ties a rating to an account.

The summary is counts only, per model: how often each one helped, and the
reasons people gave when it didn't. That is what the next training run is
chosen from.
"""
from __future__ import annotations

import re

from flask import Blueprint, jsonify, request
from sqlalchemy import func

from .. import db
from ..limiter import limiter
from ..models.compose_feedback import REASONS, VOTES, ComposeFeedback

bp = Blueprint("compose_feedback", __name__)

FIELDS = {"vote", "reasons", "model", "kept_as_written", "after_card"}
FLAGS = ("kept_as_written", "after_card")
# One rating per rewrite; nobody rates more than a handful in a sitting.
FEEDBACK_LIMITS = "20 per minute; 200 per hour"
_MODEL = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


@bp.post("")
@limiter.limit(FEEDBACK_LIMITS)
def add_feedback():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Expected a JSON object."}), 400
    # Not echoed back: an unexpected field could be the message itself.
    if set(body) - FIELDS:
        return jsonify({"error": "Unexpected field."}), 400

    vote = body.get("vote")
    if vote not in VOTES:
        return jsonify({"error": "vote must be 'up' or 'down'."}), 400
    reasons = body.get("reasons", [])
    if not isinstance(reasons, list) or not all(isinstance(r, str) and r in REASONS for r in reasons):
        return jsonify({"error": "reasons must be a list of known reason codes."}), 400
    model = body.get("model")
    if not isinstance(model, str) or not _MODEL.match(model):
        return jsonify({"error": "Missing or invalid model."}), 400
    flags = {key: body.get(key, False) for key in FLAGS}
    # bool only: 1 and "yes" are not answers to a yes/no question here
    if not all(isinstance(value, bool) for value in flags.values()):
        return jsonify({"error": "kept_as_written and after_card must be true or false."}), 400

    db.session.add(ComposeFeedback(
        vote=vote,
        reasons=",".join(code for code in REASONS if code in reasons),  # fixed order, no repeats
        model=model,
        **flags,
    ))
    db.session.commit()
    return jsonify({"ok": True}), 201


@bp.get("/summary")
def summary():
    """Ratings per model, most rated first."""
    grouped = (
        db.session.query(
            ComposeFeedback.model,
            ComposeFeedback.vote,
            ComposeFeedback.reasons,
            ComposeFeedback.kept_as_written,
            ComposeFeedback.after_card,
            func.count(),
        )
        .group_by(
            ComposeFeedback.model,
            ComposeFeedback.vote,
            ComposeFeedback.reasons,
            ComposeFeedback.kept_as_written,
            ComposeFeedback.after_card,
        )
        .all()
    )
    models: dict[str, dict] = {}
    for model, vote, reasons, kept, after_card, count in grouped:
        row = models.setdefault(model, {
            "model": model, "ratings": 0, "up": 0, "down": 0, "reasons": {},
            "kept_as_written": {"up": 0, "down": 0}, "after_card": {"up": 0, "down": 0},
        })
        row["ratings"] += count
        row[vote] += count
        for code in filter(None, reasons.split(",")):
            row["reasons"][code] = row["reasons"].get(code, 0) + count
        if kept:
            row["kept_as_written"][vote] += count
        if after_card:
            row["after_card"][vote] += count
    for row in models.values():
        row["helpful_rate"] = round(row["up"] / row["ratings"], 3)
    return jsonify({"models": sorted(models.values(), key=lambda r: -r["ratings"])}), 200
