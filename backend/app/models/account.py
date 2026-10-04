"""Accounts: a short handle, and the passkeys that prove who holds it.

What is deliberately NOT here: no email, no name, no password hash, and no
message text. An account exists so that progress and activity can follow a
reader between devices; everything it stores is either a public key or a
count. The saved cards themselves stay in the browser (see
docs/api-contract.md, "Data retention").

The handle is an address, never a credential. Four characters is about a
million combinations, which anyone can walk through in an afternoon - so
knowing a handle must not grant anything. Authentication is the passkey,
always; the handle is for "which account is this" and for telling a
teammate which one to look at.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from .. import db

# Crockford's alphabet: no I, L, O or U. The first three are the pairs people
# mistype when reading a code off a screen, and dropping U keeps accidental
# words out of a four-character handle.
HANDLE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
HANDLE_LENGTH = 4


def new_handle() -> str:
    """A random handle. Uniqueness is the database's job, not this one."""
    return "".join(secrets.choice(HANDLE_ALPHABET) for _ in range(HANDLE_LENGTH))


# Six characters out of the same alphabet is about a billion codes. With a
# ten-minute life, one use, and a rate limit in front, guessing one is not a
# route in - but it is long enough to read down a phone line, which is the
# situation it exists for.
PAIRING_CODE_LENGTH = 6
PAIRING_CODE_TTL_MINUTES = 10


def new_pairing_code() -> str:
    return "".join(secrets.choice(HANDLE_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))


def hash_pairing_code(code: str) -> str:
    """Codes are compared by hash, and only the hash is stored."""
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(db.Model):
    __tablename__ = "users"

    # A real UUID internally, so nothing downstream ever keys on the short
    # handle - which is guessable, and which a reader may one day want to
    # change.
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    handle = db.Column(db.String(8), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now)

    # No passive_deletes: the ORM deletes the passkeys itself rather than
    # trusting the database to cascade. The FK still says ON DELETE CASCADE,
    # which covers a DELETE run by hand in psql - but "delete my account"
    # must not quietly leave credentials behind on an engine that does not
    # enforce foreign keys. SQLite is exactly that engine by default, and
    # the test suite caught it.
    credentials = db.relationship(
        "Credential",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    pairing_codes = db.relationship(
        "PairingCode",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    cards = db.relationship(
        "UserCard",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict:
        return {
            "handle": self.handle,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PairingCode(db.Model):
    """A short-lived permission to register a passkey on a second device.

    The problem it solves: a passkey cannot travel. Typing a handle on a new
    laptop proves nothing, because WebAuthn needs the private key present -
    so without this, an account is stranded on whichever browser made it
    unless its password manager happens to sync.

    What this is NOT is a password. It is generated on demand, lives ten
    minutes, works once, is stored only as a hash, and grants exactly one
    thing: the right to add a key. Nothing signs in with it.
    """

    __tablename__ = "pairing_codes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Hashed, like any other bearer secret: a database dump should not hand
    # over the live codes with it.
    code_hash = db.Column(db.String(64), unique=True, nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    consumed_at = db.Column(db.DateTime(timezone=True))

    user = db.relationship("User", back_populates="pairing_codes")

    @property
    def is_usable(self) -> bool:
        if self.consumed_at is not None:
            return False
        expires = self.expires_at
        # SQLite hands back naive datetimes even for a timezone=True column,
        # so compare on equal footing rather than crashing on the subtraction.
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires > _now()


class Credential(db.Model):
    """One passkey. A reader may register several - phone, laptop, key."""

    __tablename__ = "credentials"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.String(36), db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # The authenticator's own id for this key, and the public half of the
    # pair. The private half never leaves the reader's device - that is the
    # whole reason this is not a password.
    credential_id = db.Column(db.LargeBinary, unique=True, nullable=False)
    public_key = db.Column(db.LargeBinary, nullable=False)

    # The authenticator increments this on every use. A counter that goes
    # backwards means the key has been cloned, which the library checks for -
    # so it has to be stored and updated, not just recorded once.
    sign_count = db.Column(db.Integer, nullable=False, default=0)
    transports = db.Column(db.String(120))

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=_now)
    last_used_at = db.Column(db.DateTime(timezone=True))

    user = db.relationship("User", back_populates="credentials")
