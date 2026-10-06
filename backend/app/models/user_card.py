"""Library cards an account carries between devices.

Only cards saved from the pattern library live here, and only as a pointer:
which curated row, when it was kept, when it was last opened. The pattern's
own text is already on the server - it is content the team wrote, not
anything the reader typed.

Cards saved from a decode are deliberately NOT in this table. They carry an
excerpt of the reader's own message, and message text never leaves the
browser (see docs/api-contract.md, "Data retention"). The cost is that those
cards stay on the device that made them; the alternative was uploading
people's work messages, which is not a trade this project makes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .. import db


def _now() -> datetime:
    return datetime.now(timezone.utc)


class UserCard(db.Model):
    __tablename__ = "user_cards"
    # One row per pattern per account: keeping the same library row twice is
    # not a second card, it is the same card.
    __table_args__ = (db.UniqueConstraint("user_id", "pattern_id", name="uq_user_cards_user_pattern"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # A string, like the id the patterns API hands out - the table's own key
    # is an integer, but every client sees it as text.
    pattern_id = db.Column(db.String(40), nullable=False)

    saved_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now)
    last_opened_at = db.Column(db.DateTime(timezone=True))

    user = db.relationship("User", back_populates="cards")

    def to_dict(self) -> dict:
        return {
            "pattern_id": self.pattern_id,
            "saved_at": self.saved_at.isoformat() if self.saved_at else None,
            "last_opened_at": self.last_opened_at.isoformat() if self.last_opened_at else None,
        }
