"""Progress-dashboard data an account carries between devices.

Same reasoning as user_card.py: only pointers and counts, never anything the
reader typed. Two tables:

- user_activity: minutes per feature per day, per device. A day the app was
  opened at all is a row with feature "opened" and 0 minutes - that is what
  the badges count.
- user_phrase_events: which library pattern was viewed or reviewed, and on
  which day. That is what the refresher and the library progress read.

The focus timer's "what are you working on?" text is free text, so it is NOT
here. It stays in the browser that wrote it.

Why activity is keyed by device: two devices can both log Decoder time on the
same day, and the server has to add them up without double counting when a
device replays everything it has. Each device only ever owns its own rows, so
a replay is an overwrite of the same numbers, never a second copy. The device
id is a random string the browser makes for itself; it says nothing about the
person or the machine.
"""
from __future__ import annotations

from .. import db

FEATURES = ("opened", "decoder", "compose", "study", "library")
PHRASE_KINDS = ("viewed", "reviewed")


class UserActivity(db.Model):
    __tablename__ = "user_activity"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "device_id", "date", "feature", name="uq_user_activity_user_device_day_feature"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id = db.Column(db.String(36), nullable=False)
    # The reader's own calendar day, YYYY-MM-DD, as the browser saw it. A
    # date and not a timestamp: "did they show up on Tuesday" is about their
    # Tuesday, not the server's.
    date = db.Column(db.String(10), nullable=False)
    feature = db.Column(db.String(16), nullable=False)
    minutes = db.Column(db.Integer, nullable=False, default=0)

    # Defined from this side so models/account.py doesn't need touching.
    # The cascade is what makes "delete my account" take these rows with it
    # (SQLite doesn't enforce the foreign key on its own - see docs/accounts.md).
    user = db.relationship(
        "User", backref=db.backref("progress_activity", cascade="all, delete-orphan")
    )

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "date": self.date,
            "feature": self.feature,
            "minutes": self.minutes,
        }


class UserPhraseEvent(db.Model):
    __tablename__ = "user_phrase_events"
    __table_args__ = (
        db.UniqueConstraint(
            "user_id", "pattern_id", "kind", "date", name="uq_user_phrase_events_user_pattern_kind_day"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pattern_id = db.Column(db.String(40), nullable=False)
    kind = db.Column(db.String(10), nullable=False)
    date = db.Column(db.String(10), nullable=False)

    user = db.relationship(
        "User", backref=db.backref("progress_phrase_events", cascade="all, delete-orphan")
    )

    def to_dict(self) -> dict:
        return {"pattern_id": self.pattern_id, "kind": self.kind, "date": self.date}
