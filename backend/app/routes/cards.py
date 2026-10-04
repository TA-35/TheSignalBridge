"""GET/PUT/DELETE /api/cards - the library cards an account carries.

Three endpoints, all requiring a session, all dealing in pattern ids and
timestamps. No message text passes through here; see app/models/user_card.py
for why only library cards are syncable at all.

The browser stays the source of truth for what the reader sees. This is a
copy that lets a second device start from the same place, not a store the
Study page reads from - so every write is best-effort from the client's
point of view, and a failure here never costs anyone a saved card.
"""
from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request, session

from .. import db
from ..models.account import User
from ..models.user_card import UserCard

bp = Blueprint("cards", __name__)

USER_KEY = "user_id"


def _current_user() -> User | None:
    user_id = session.get(USER_KEY)
    if not user_id:
        return None
    return db.session.get(User, user_id)


def _parse_time(value) -> datetime | None:
    """An ISO timestamp from the client, or None.

    Times come from the device that saved the card, because that is where
    the action happened - a card kept offline yesterday should not claim to
    be from the moment it first managed to sync.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@bp.get("")
def list_cards():
    user = _current_user()
    if user is None:
        return jsonify({"error": "Not signed in."}), 401
    rows = UserCard.query.filter_by(user_id=user.id).all()
    return jsonify([row.to_dict() for row in rows]), 200


@bp.put("/<pattern_id>")
def upsert_card(pattern_id: str):
    """Keep a library card, or update when it was last opened.

    Idempotent on purpose: the client replays its whole local set after
    signing in on a new device, and saving the same card twice is not an
    error - it is the normal case.
    """
    user = _current_user()
    if user is None:
        return jsonify({"error": "Not signed in."}), 401
    if len(pattern_id) > 40:
        return jsonify({"error": "Unknown pattern."}), 400

    body = request.get_json(silent=True) or {}
    saved_at = _parse_time(body.get("saved_at"))
    last_opened_at = _parse_time(body.get("last_opened_at"))

    card = UserCard.query.filter_by(user_id=user.id, pattern_id=pattern_id).first()
    if card is None:
        card = UserCard(
            user_id=user.id,
            pattern_id=pattern_id,
            saved_at=saved_at or datetime.now(timezone.utc),
            last_opened_at=last_opened_at,
        )
        db.session.add(card)
    else:
        # Later wins, in both directions: two devices disagreeing about a
        # card means one of them opened it more recently, and that is the
        # fact worth keeping.
        if saved_at and (card.saved_at is None or saved_at < _aware(card.saved_at)):
            card.saved_at = saved_at
        if last_opened_at and (
            card.last_opened_at is None or last_opened_at > _aware(card.last_opened_at)
        ):
            card.last_opened_at = last_opened_at

    db.session.commit()
    return jsonify(card.to_dict()), 200


@bp.delete("/<pattern_id>")
def delete_card(pattern_id: str):
    user = _current_user()
    if user is None:
        return jsonify({"error": "Not signed in."}), 401

    UserCard.query.filter_by(user_id=user.id, pattern_id=pattern_id).delete()
    db.session.commit()
    # 200 whether or not a row was there: deleting a card the server never
    # had is the client and server agreeing, not a failure.
    return jsonify({"ok": True}), 200


def _aware(value: datetime) -> datetime:
    """SQLite hands back naive datetimes even for a timezone=True column."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
