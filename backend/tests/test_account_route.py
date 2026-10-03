"""Account endpoints.

What is tested here is the plumbing around WebAuthn - the session handling,
the handle, the failure shapes, and that deleting an account really removes
it. The signature check itself is py_webauthn's, exercised against its own
test vectors upstream; reproducing a real authenticator here would test the
library rather than this code, so verification is stubbed and what happens
either side of it is what gets asserted.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app import create_app, db
from app.config import Config
from app.models.account import (
    HANDLE_ALPHABET,
    HANDLE_LENGTH,
    Credential,
    PairingCode,
    User,
    hash_pairing_code,
    new_handle,
)


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WEBAUTHN_RP_ID = "localhost"
    WEBAUTHN_ORIGINS = ["http://localhost:5173"]
    # SQLite in memory plus a Secure cookie means the test client never sends
    # the session back, because the test client speaks http.
    SESSION_COOKIE_SECURE = False


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _fake_registration(credential_id=b"cred-1", public_key=b"pub-1", sign_count=0):
    return SimpleNamespace(
        credential_id=credential_id,
        credential_public_key=public_key,
        sign_count=sign_count,
    )


def register(client, monkeypatch, credential_id=b"cred-1"):
    """Walk the two-step registration with the signature check stubbed."""
    assert client.post("/api/account/register/options").status_code == 200
    monkeypatch.setattr(
        "app.routes.account.webauthn.verify_registration_response",
        lambda **_: _fake_registration(credential_id=credential_id),
    )
    return client.post("/api/account/register/verify", json={"id": "x"})


# ---------------------------------------------------------------------------
# Handles
# ---------------------------------------------------------------------------

def test_handle_is_four_characters_from_the_unambiguous_alphabet():
    for _ in range(200):
        handle = new_handle()
        assert len(handle) == HANDLE_LENGTH
        assert set(handle) <= set(HANDLE_ALPHABET)
        # The pairs people mistype reading a code aloud are not in play.
        assert not set(handle) & set("ILOU")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def test_register_options_returns_a_challenge_without_creating_a_user(client, app):
    response = client.post("/api/account/register/options")

    assert response.status_code == 200
    assert response.get_json()["challenge"]
    # A reader who opens the dialog and walks away leaves nothing behind.
    with app.app_context():
        assert User.query.count() == 0


def test_register_verify_creates_the_account_and_signs_it_in(client, app, monkeypatch):
    response = register(client, monkeypatch)

    assert response.status_code == 201
    handle = response.get_json()["handle"]
    assert len(handle) == HANDLE_LENGTH

    with app.app_context():
        assert User.query.count() == 1
        assert Credential.query.count() == 1

    assert client.get("/api/account/me").get_json()["handle"] == handle


def test_register_verify_without_starting_is_rejected(client):
    response = client.post("/api/account/register/verify", json={"id": "x"})

    assert response.status_code == 400
    assert "error" in response.get_json()


def test_register_verify_rejects_an_unverifiable_passkey(client, app, monkeypatch):
    client.post("/api/account/register/options")

    def boom(**_):
        raise ValueError("bad attestation")

    monkeypatch.setattr("app.routes.account.webauthn.verify_registration_response", boom)
    response = client.post("/api/account/register/verify", json={"id": "x"})

    assert response.status_code == 400
    # The library's message quotes the response it was handed, which is the
    # reader's own device data - it must not travel back over the wire.
    assert "attestation" not in response.get_json()["error"]
    with app.app_context():
        assert User.query.count() == 0


def test_a_challenge_is_single_use(client, monkeypatch):
    register(client, monkeypatch)
    # Replaying the same verify call now that the challenge is spent.
    assert client.post("/api/account/register/verify", json={"id": "x"}).status_code == 400


# ---------------------------------------------------------------------------
# Signing in
# ---------------------------------------------------------------------------

def test_login_verifies_and_restores_the_same_account(client, app, monkeypatch):
    handle = register(client, monkeypatch).get_json()["handle"]
    client.post("/api/account/logout")
    assert client.get("/api/account/me").status_code == 401

    client.post("/api/account/login/options")
    monkeypatch.setattr(
        "app.routes.account.webauthn.verify_authentication_response",
        lambda **_: SimpleNamespace(new_sign_count=7),
    )
    response = client.post("/api/account/login/verify", json={"rawId": "Y3JlZC0x"})  # "cred-1"

    assert response.status_code == 200
    assert response.get_json()["handle"] == handle
    with app.app_context():
        assert Credential.query.one().sign_count == 7


def test_login_with_an_unknown_passkey_is_rejected(client, monkeypatch):
    register(client, monkeypatch)
    client.post("/api/account/logout")
    client.post("/api/account/login/options")

    response = client.post("/api/account/login/verify", json={"rawId": "bm9wZQ"})  # "nope"

    assert response.status_code == 400
    # Same wording as a failed signature: telling the two apart would let a
    # prober map which credential ids exist.
    assert response.get_json()["error"] == "That passkey could not be verified."


# ---------------------------------------------------------------------------
# The session
# ---------------------------------------------------------------------------

def test_me_is_401_when_signed_out(client):
    assert client.get("/api/account/me").status_code == 401


def test_delete_removes_the_account_and_its_passkeys(client, app, monkeypatch):
    register(client, monkeypatch)

    assert client.delete("/api/account").status_code == 200

    with app.app_context():
        assert User.query.count() == 0
        assert Credential.query.count() == 0
    assert client.get("/api/account/me").status_code == 401


def test_delete_when_signed_out_is_401(client):
    assert client.delete("/api/account").status_code == 401


# ---------------------------------------------------------------------------
# Pairing a second device
# ---------------------------------------------------------------------------

def test_pairing_code_needs_a_signed_in_device(client):
    assert client.post("/api/account/pairing").status_code == 401


def test_a_second_device_can_pair_and_ends_up_with_its_own_passkey(app, monkeypatch):
    laptop = app.test_client()
    handle = register(laptop, monkeypatch, credential_id=b"laptop-key").get_json()["handle"]

    code = laptop.post("/api/account/pairing").get_json()["code"]
    assert len(code) == 6

    # A different client is a different browser: no session, no passkey.
    phone = app.test_client()
    assert phone.get("/api/account/me").status_code == 401

    claim = phone.post("/api/account/pairing/claim", json={"handle": handle, "code": code})
    assert claim.status_code == 200
    assert claim.get_json()["challenge"]

    monkeypatch.setattr(
        "app.routes.account.webauthn.verify_registration_response",
        lambda **_: _fake_registration(credential_id=b"phone-key"),
    )
    verified = phone.post("/api/account/pairing/verify", json={"id": "x"})

    assert verified.status_code == 201
    # The same account, not a second one.
    assert verified.get_json()["handle"] == handle
    with app.app_context():
        assert User.query.count() == 1
        assert Credential.query.count() == 2

    # And from here the new device stands on its own passkey.
    assert phone.get("/api/account/me").get_json()["handle"] == handle


def test_a_code_works_once(app, monkeypatch):
    laptop = app.test_client()
    handle = register(laptop, monkeypatch).get_json()["handle"]
    code = laptop.post("/api/account/pairing").get_json()["code"]

    first = app.test_client()
    assert first.post("/api/account/pairing/claim", json={"handle": handle, "code": code}).status_code == 200

    second = app.test_client()
    replay = second.post("/api/account/pairing/claim", json={"handle": handle, "code": code})
    assert replay.status_code == 400


def test_asking_for_a_new_code_retires_the_old_one(app, monkeypatch):
    laptop = app.test_client()
    handle = register(laptop, monkeypatch).get_json()["handle"]
    first_code = laptop.post("/api/account/pairing").get_json()["code"]
    laptop.post("/api/account/pairing")

    phone = app.test_client()
    response = phone.post("/api/account/pairing/claim", json={"handle": handle, "code": first_code})

    assert response.status_code == 400


def test_an_expired_code_is_refused(app, monkeypatch):
    laptop = app.test_client()
    handle = register(laptop, monkeypatch).get_json()["handle"]
    code = laptop.post("/api/account/pairing").get_json()["code"]

    with app.app_context():
        record = PairingCode.query.one()
        record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()

    phone = app.test_client()
    assert phone.post("/api/account/pairing/claim", json={"handle": handle, "code": code}).status_code == 400


def test_the_code_must_match_its_own_handle(app, monkeypatch):
    laptop = app.test_client()
    register(laptop, monkeypatch)
    code = laptop.post("/api/account/pairing").get_json()["code"]

    phone = app.test_client()
    response = phone.post("/api/account/pairing/claim", json={"handle": "ZZZZ", "code": code})

    assert response.status_code == 400
    # Wrong handle, wrong code, expired code and unknown account all answer
    # the same way, so this cannot be used to discover which handles exist.
    assert response.get_json()["error"] == "That code is not valid. Ask for a new one."


def test_only_the_hash_of_a_code_is_stored(app, monkeypatch):
    laptop = app.test_client()
    register(laptop, monkeypatch)
    code = laptop.post("/api/account/pairing").get_json()["code"]

    with app.app_context():
        stored = PairingCode.query.one().code_hash
        assert code not in stored
        assert stored == hash_pairing_code(code)


def test_claiming_does_not_sign_the_device_in_by_itself(app, monkeypatch):
    """The code buys a registration, never a session."""
    laptop = app.test_client()
    handle = register(laptop, monkeypatch).get_json()["handle"]
    code = laptop.post("/api/account/pairing").get_json()["code"]

    phone = app.test_client()
    phone.post("/api/account/pairing/claim", json={"handle": handle, "code": code})

    # Claimed, but no passkey registered yet - so still nobody.
    assert phone.get("/api/account/me").status_code == 401


def test_deleting_an_account_takes_its_pairing_codes(app, monkeypatch):
    laptop = app.test_client()
    register(laptop, monkeypatch)
    laptop.post("/api/account/pairing")

    laptop.delete("/api/account")

    with app.app_context():
        assert PairingCode.query.count() == 0


# ---------------------------------------------------------------------------
# The rest of the API is untouched by any of this
# ---------------------------------------------------------------------------

def test_decode_still_works_signed_out(client):
    response = client.post("/api/decode", json={"message": "Send the report by Friday."})

    assert response.status_code == 200
