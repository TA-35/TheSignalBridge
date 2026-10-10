"""GET/PUT/DELETE /api/progress - the dashboard data an account carries.

Built the same way as routes/cards.py: signed in only, PUT is an idempotent
upsert so a device can replay everything it has after signing in, and the
browser stays the source of truth. A failed sync never costs anyone their
days or their badges, because the browser still has them.

One endpoint for the whole set rather than one call per row: a device signing
in for the first time may have a few hundred small rows, and that should be
one request, not hundreds.

What travels: dates, feature names, minute counts, pattern ids. What doesn't:
the focus timer's free-text intent, and anything from a decoded message.
"""
from __future__ import annotations

import re
from datetime import date as Date

from flask import Blueprint, jsonify, request, session

from .. import db
from ..models.account import User
from ..models.user_progress import FEATURES, PHRASE_KINDS, UserActivity, UserPhraseEvent

bp = Blueprint("progress", __name__)

USER_KEY = "user_id"

# Generous for a year of use, small enough that one request can't fill a table.
MAX_ACTIVITY_ROWS = 2000
MAX_PHRASE_EVENTS = 5000
MAX_MINUTES_PER_DAY = 24 * 60

_DEVICE_ID = re.compile(r"^[A-Za-z0-9_-]{8,36}$")


def _current_user() -> User | None:
    user_id = session.get(USER_KEY)
    if not user_id:
        return None
    return db.session.get(User, user_id)


def _day(value) -> str | None:
    """A YYYY-MM-DD string that is a real calendar day, or None."""
    if not isinstance(value, str) or len(value) != 10:
        return None
    try:
        return Date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _minutes(value) -> int | None:
    # bool is an int in Python; true minutes is not a thing
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 0 <= value <= MAX_MINUTES_PER_DAY else None


def _snapshot(user: User) -> dict:
    return {
        "activity": [row.to_dict() for row in UserActivity.query.filter_by(user_id=user.id)],
        "phrase_events": [row.to_dict() for row in UserPhraseEvent.query.filter_by(user_id=user.id)],
    }


@bp.get("")
def get_progress():
    user = _current_user()
    if user is None:
        return jsonify({"error": "Not signed in."}), 401
    return jsonify(_snapshot(user)), 200


@bp.put("")
def put_progress():
    """Merge what one device has into the account, then return the whole set.

    Rows that don't parse are skipped rather than failing the request: one
    odd row from an old browser shouldn't block every sync after it. The
    count comes back as `skipped` so it shows up in the network tab.
    """
    user = _current_user()
    if user is None:
        return jsonify({"error": "Not signed in."}), 401

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Expected a JSON object."}), 400

    device_id = body.get("device_id")
    if not isinstance(device_id, str) or not _DEVICE_ID.match(device_id):
        return jsonify({"error": "Missing or invalid device_id."}), 400

    activity = body.get("activity") or []
    events = body.get("phrase_events") or []
    if not isinstance(activity, list) or not isinstance(events, list):
        return jsonify({"error": "activity and phrase_events must be lists."}), 400
    if len(activity) > MAX_ACTIVITY_ROWS or len(events) > MAX_PHRASE_EVENTS:
        return jsonify({"error": "Too much progress in one request."}), 413

    skipped = 0

    # ---- minutes: this device's own rows only, highest count wins.
    # A browser's total for a day only ever goes up, so "max" makes a replay
    # (or two requests arriving out of order) harmless.
    existing = {
        (row.date, row.feature): row
        for row in UserActivity.query.filter_by(user_id=user.id, device_id=device_id)
    }
    for item in activity:
        day = _day(item.get("date")) if isinstance(item, dict) else None
        feature = item.get("feature") if isinstance(item, dict) else None
        minutes = _minutes(item.get("minutes")) if isinstance(item, dict) else None
        if day is None or feature not in FEATURES or minutes is None:
            skipped += 1
            continue
        row = existing.get((day, feature))
        if row is None:
            row = UserActivity(
                user_id=user.id, device_id=device_id, date=day, feature=feature, minutes=minutes
            )
            db.session.add(row)
            existing[(day, feature)] = row
        elif minutes > row.minutes:
            row.minutes = minutes

    # ---- viewed / reviewed: a set, so it's insert-if-missing
    seen = {
        (row.pattern_id, row.kind, row.date)
        for row in UserPhraseEvent.query.filter_by(user_id=user.id)
    }
    for item in events:
        pattern_id = item.get("pattern_id") if isinstance(item, dict) else None
        kind = item.get("kind") if isinstance(item, dict) else None
        day = _day(item.get("date")) if isinstance(item, dict) else None
        if (
            not isinstance(pattern_id, str)
            or not 0 < len(pattern_id) <= 40
            or kind not in PHRASE_KINDS
            or day is None
        ):
            skipped += 1
            continue
        key = (pattern_id, kind, day)
        if key in seen:
            continue
        seen.add(key)
        db.session.add(UserPhraseEvent(user_id=user.id, pattern_id=pattern_id, kind=kind, date=day))

    db.session.commit()
    return jsonify({**_snapshot(user), "skipped": skipped}), 200


@bp.delete("")
def delete_progress():
    """Settings' "delete" while signed in. Without this, clearing progress in
    the browser would just sync it straight back down on the next sign-in."""
    user = _current_user()
    if user is None:
        return jsonify({"error": "Not signed in."}), 401
    UserActivity.query.filter_by(user_id=user.id).delete()
    UserPhraseEvent.query.filter_by(user_id=user.id).delete()
    db.session.commit()
    return jsonify({"ok": True}), 200
