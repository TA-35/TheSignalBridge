"""A 👍/👎 on a Compose rewrite.

No text of any kind: not the draft, not the rewrite, not a comment. The privacy
page promises messages are never stored, so a rating is only what can't carry
a message - the vote, reasons picked from a fixed list, which model wrote the
rewrite, and two yes/no facts about how it was reached. That is enough to see
how often each model helps, and what goes wrong when it doesn't, to choose
what the next training run needs.

Not tied to an account, so it says nothing about who rated what.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .. import db

VOTES = ("up", "down")

# What went wrong, as the sender picks it. The codes are stored; the labels
# live in the frontend (services/composeService.ts) and can change freely.
REASONS = (
    "changed_meaning",  # it now says something I didn't mean
    "left_out",         # a detail from my draft is missing
    "added",            # it says something my draft didn't
    "still_unclear",    # the reader would still have to guess
    "too_blunt",        # clear, but cold or rude
    "notes_wrong",      # the "what changed and why" notes don't match the rewrite
    "needed_rewrite",   # "already clear", but it wasn't
)


class ComposeFeedback(db.Model):
    __tablename__ = "compose_feedback"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    # The name the inference service reports, e.g. "qwen3.5-4b-ft-run2".
    model = db.Column(db.String(64), nullable=False, index=True)
    vote = db.Column(db.String(4), nullable=False)
    # Codes from REASONS joined with commas; "" for none.
    reasons = db.Column(db.String(200), nullable=False, default="")
    # The model said the draft was already clear and kept it as written.
    kept_as_written = db.Column(db.Boolean, nullable=False, default=False)
    # The sender answered the "what's missing" questions before this rewrite.
    after_card = db.Column(db.Boolean, nullable=False, default=False)
