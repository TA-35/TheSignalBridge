"""Accounts, held by a passkey.

Four endpoints do the work, in two pairs. Each pair is "ask the browser a
question" then "check the answer":

    POST /register/options  ->  POST /register/verify
    POST /login/options     ->  POST /login/verify

The challenge the browser signs is kept in the Flask session between the two
calls, not in a table. It is single-use, short-lived, and meaningless to
anyone who does not also hold the private key, so a signed cookie is the
right place for it - and it means a half-finished registration leaves nothing
behind to clean up.

No row is written until a registration verifies. The handle and the user id
are generated in /register/options and carried in the session, so a reader
who opens the dialog and changes their mind does not leave an empty account
with a handle reserved for nobody.

WHY A PASSKEY AND NOT A PASSWORD

The project is not allowed to hold passwords. A passkey is not one: the
private key stays in the reader's device, the server stores only the public
half, and there is nothing here worth stealing in a database dump.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import webauthn
from flask import Blueprint, current_app, jsonify, request, session
from sqlalchemy.exc import IntegrityError
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url, options_to_json
from webauthn.helpers.exceptions import (
    InvalidAuthenticationResponse,
    InvalidRegistrationResponse,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from .. import db
from ..limiter import limiter
from ..models.account import (
    PAIRING_CODE_TTL_MINUTES,
    Credential,
    PairingCode,
    User,
    hash_pairing_code,
    new_handle,
    new_pairing_code,
)

bp = Blueprint("account", __name__)

# Session keys. Prefixed so a future feature putting its own data in the
# session cannot collide with a half-finished registration.
CHALLENGE_KEY = "wa_challenge"
PENDING_USER_KEY = "wa_pending_user"
PENDING_HANDLE_KEY = "wa_pending_handle"
USER_KEY = "user_id"
# Set by a redeemed pairing code: "this browser may add a key to that
# account, and nothing else". Not a session - /me still says signed out
# until a passkey has actually been registered.
PAIRING_USER_KEY = "wa_pairing_user"

# A handle is four characters out of a 32-letter alphabet. Collisions are
# rare but not negligible once there are a few thousand accounts, and the
# unique index is what actually decides - this is how many times to re-roll
# before giving up and asking the reader to try again.
HANDLE_ATTEMPTS = 8


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rp_id() -> str:
    return current_app.config["WEBAUTHN_RP_ID"]


def _origins() -> list[str]:
    return list(current_app.config["WEBAUTHN_ORIGINS"])


def _current_user() -> User | None:
    user_id = session.get(USER_KEY)
    if not user_id:
        return None
    return db.session.get(User, user_id)


def _sign_in(user: User) -> None:
    session.clear()
    session[USER_KEY] = user.id
    session.permanent = True
    user.last_seen_at = _now()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@bp.post("/register/options")
@limiter.limit("20 per hour")
def register_options():
    import uuid

    user_id = str(uuid.uuid4())
    handle = new_handle()

    options = webauthn.generate_registration_options(
        rp_id=_rp_id(),
        rp_name=current_app.config["WEBAUTHN_RP_NAME"],
        # The authenticator shows these to the reader when it asks them to
        # confirm. There is no email or name to show, so the handle is it.
        user_id=user_id.encode("utf-8"),
        user_name=handle,
        user_display_name=f"BetweenWords {handle}",
        authenticator_selection=AuthenticatorSelectionCriteria(
            # Discoverable, so signing in later needs no handle typed in:
            # the browser offers the accounts it holds for this site.
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    session[CHALLENGE_KEY] = bytes_to_base64url(options.challenge)
    session[PENDING_USER_KEY] = user_id
    session[PENDING_HANDLE_KEY] = handle

    return current_app.response_class(
        options_to_json(options), mimetype="application/json"
    )


@bp.post("/register/verify")
@limiter.limit("20 per hour")
def register_verify():
    challenge = session.pop(CHALLENGE_KEY, None)
    user_id = session.pop(PENDING_USER_KEY, None)
    handle = session.pop(PENDING_HANDLE_KEY, None)
    if not challenge or not user_id or not handle:
        return jsonify({"error": "Start again - this sign-up has expired."}), 400

    try:
        verified = webauthn.verify_registration_response(
            credential=request.get_json(silent=True) or {},
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=_rp_id(),
            expected_origin=_origins(),
        )
    except (InvalidRegistrationResponse, ValueError, KeyError):
        # Never echo the library's message: it quotes the response it was
        # given, which is the reader's own device data.
        return jsonify({"error": "That passkey could not be verified."}), 400

    # Re-roll the handle rather than the whole registration if the unique
    # index rejects it - the passkey is already made at this point, and
    # making the reader do it again over a name collision would be absurd.
    for attempt in range(HANDLE_ATTEMPTS):
        user = User(id=user_id, handle=handle)
        credential = Credential(
            user_id=user_id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
        )
        db.session.add(user)
        db.session.add(credential)
        try:
            db.session.commit()
            break
        except IntegrityError:
            db.session.rollback()
            if attempt == HANDLE_ATTEMPTS - 1:
                return jsonify({"error": "Could not create an account. Please try again."}), 409
            handle = new_handle()
    else:  # pragma: no cover - the loop always breaks or returns
        return jsonify({"error": "Could not create an account. Please try again."}), 409

    _sign_in(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


# ---------------------------------------------------------------------------
# Signing in
# ---------------------------------------------------------------------------

@bp.post("/login/options")
@limiter.limit("30 per hour")
def login_options():
    # No allow_credentials: the passkey is discoverable, so the browser knows
    # which accounts it holds for this site and the server does not have to
    # be told who is signing in before they have proved it.
    options = webauthn.generate_authentication_options(
        rp_id=_rp_id(),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    session[CHALLENGE_KEY] = bytes_to_base64url(options.challenge)

    return current_app.response_class(
        options_to_json(options), mimetype="application/json"
    )


@bp.post("/login/verify")
@limiter.limit("30 per hour")
def login_verify():
    challenge = session.pop(CHALLENGE_KEY, None)
    if not challenge:
        return jsonify({"error": "Start again - this sign-in has expired."}), 400

    body = request.get_json(silent=True) or {}
    raw_id = body.get("rawId") or body.get("id")
    if not isinstance(raw_id, str):
        return jsonify({"error": "That passkey could not be verified."}), 400

    try:
        credential_id = base64url_to_bytes(raw_id)
    except Exception:  # noqa: BLE001 - malformed base64url from the client
        return jsonify({"error": "That passkey could not be verified."}), 400

    credential = Credential.query.filter_by(credential_id=credential_id).first()
    # Same message as a failed signature, on purpose: "no such passkey" and
    # "wrong signature" together would tell a prober which guesses exist.
    if credential is None:
        return jsonify({"error": "That passkey could not be verified."}), 400

    try:
        verified = webauthn.verify_authentication_response(
            credential=body,
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=_rp_id(),
            expected_origin=_origins(),
            credential_public_key=credential.public_key,
            credential_current_sign_count=credential.sign_count,
        )
    except (InvalidAuthenticationResponse, ValueError, KeyError):
        return jsonify({"error": "That passkey could not be verified."}), 400

    credential.sign_count = verified.new_sign_count
    credential.last_used_at = _now()
    user = credential.user
    _sign_in(user)
    db.session.commit()

    return jsonify(user.to_dict()), 200


# ---------------------------------------------------------------------------
# Adding a second device
#
# A passkey cannot be copied to another machine, so an account made on a
# laptop is stranded there unless that browser's password manager syncs it.
# The way out is to register a SECOND passkey on the new device - and the
# only question is what authorises that.
#
# Here it is a code shown on a device that is already signed in. The new
# device sends the handle and the code; if they match, it is allowed to
# create one passkey, and from then on it signs in on its own. The code is
# never a way in by itself: it authorises a registration, not a session.
# ---------------------------------------------------------------------------

@bp.post("/pairing")
@limiter.limit("10 per hour")
def create_pairing_code():
    user = _current_user()
    if user is None:
        return jsonify({"error": "Not signed in."}), 401

    # One live code per account. Asking for a new one invalidates the old,
    # so a code read out and then forgotten cannot be used an hour later.
    PairingCode.query.filter_by(user_id=user.id, consumed_at=None).update(
        {"consumed_at": _now()}
    )

    code = new_pairing_code()
    expires_at = _now() + timedelta(minutes=PAIRING_CODE_TTL_MINUTES)
    db.session.add(
        PairingCode(user_id=user.id, code_hash=hash_pairing_code(code), expires_at=expires_at)
    )
    db.session.commit()

    # The only time the plaintext exists. It is not stored and cannot be
    # shown again - a second look means a second code.
    return jsonify({
        "code": code,
        "handle": user.handle,
        "expires_at": expires_at.isoformat(),
        "expires_in_minutes": PAIRING_CODE_TTL_MINUTES,
    }), 201


@bp.post("/pairing/claim")
@limiter.limit("10 per hour")
def claim_pairing_code():
    """Redeem a code, and hand back options for a passkey on this device."""
    body = request.get_json(silent=True) or {}
    handle = str(body.get("handle", "")).strip().upper()
    code = str(body.get("code", "")).strip().upper()
    if not handle or not code:
        return jsonify({"error": "Enter your ID and the code from your other device."}), 400

    record = PairingCode.query.filter_by(code_hash=hash_pairing_code(code)).first()
    user = record.user if record else None
    # One message for every way this can fail - wrong code, expired code,
    # code belonging to a different account, no such handle. Telling them
    # apart would turn this into an oracle for which handles exist.
    if record is None or not record.is_usable or user is None or user.handle != handle:
        return jsonify({"error": "That code is not valid. Ask for a new one."}), 400

    # Spent on redemption rather than on success: if this browser abandons
    # the passkey prompt, the code is gone and the reader asks for another.
    # The alternative leaves a live code sitting in a closed tab.
    record.consumed_at = _now()
    db.session.commit()

    options = webauthn.generate_registration_options(
        rp_id=_rp_id(),
        rp_name=current_app.config["WEBAUTHN_RP_NAME"],
        user_id=user.id.encode("utf-8"),
        user_name=user.handle,
        user_display_name=f"BetweenWords {user.handle}",
        # The keys this account already has. The authenticator refuses to
        # make a second one for itself, which is what stops a reader pairing
        # the device they are already standing at.
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=c.credential_id) for c in user.credentials
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )

    session[CHALLENGE_KEY] = bytes_to_base64url(options.challenge)
    session[PAIRING_USER_KEY] = user.id

    return current_app.response_class(
        options_to_json(options), mimetype="application/json"
    )


@bp.post("/pairing/verify")
@limiter.limit("10 per hour")
def verify_pairing():
    challenge = session.pop(CHALLENGE_KEY, None)
    user_id = session.pop(PAIRING_USER_KEY, None)
    if not challenge or not user_id:
        return jsonify({"error": "Start again - this code has expired."}), 400

    user = db.session.get(User, user_id)
    if user is None:
        return jsonify({"error": "Start again - this code has expired."}), 400

    try:
        verified = webauthn.verify_registration_response(
            credential=request.get_json(silent=True) or {},
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=_rp_id(),
            expected_origin=_origins(),
        )
    except (InvalidRegistrationResponse, ValueError, KeyError):
        return jsonify({"error": "That passkey could not be verified."}), 400

    db.session.add(
        Credential(
            user_id=user.id,
            credential_id=verified.credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
        )
    )
    _sign_in(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


# ---------------------------------------------------------------------------
# The session itself
# ---------------------------------------------------------------------------

@bp.get("/me")
def me():
    user = _current_user()
    if user is None:
        # 401 rather than an empty 200: "nobody is signed in" is the answer
        # the frontend branches on, and it should not look like an account
        # with no data in it.
        return jsonify({"error": "Not signed in."}), 401
    return jsonify(user.to_dict()), 200


@bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True}), 200


@bp.delete("")
def delete_account():
    user = _current_user()
    if user is None:
        return jsonify({"error": "Not signed in."}), 401

    # Credentials go with the row (cascade), and there is nothing else to
    # erase: the cards and the message text were never here.
    db.session.delete(user)
    db.session.commit()
    session.clear()
    return jsonify({"ok": True}), 200
