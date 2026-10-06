"""Library cards that follow an account between devices.

The point of these: a second device signing in should find the same library
cards, and nothing else. Message text must not travel, and a signed-out
caller must get nowhere.
"""
from types import SimpleNamespace

import pytest

from app import create_app, db
from app.config import Config
from app.models.user_card import UserCard


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WEBAUTHN_RP_ID = "localhost"
    WEBAUTHN_ORIGINS = ["http://localhost:5173"]
    SESSION_COOKIE_SECURE = False


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def register(client, monkeypatch, credential_id=b"cred-1"):
    client.post("/api/account/register/options")
    monkeypatch.setattr(
        "app.routes.account.webauthn.verify_registration_response",
        lambda **_: SimpleNamespace(
            credential_id=credential_id, credential_public_key=b"pub", sign_count=0
        ),
    )
    return client.post("/api/account/register/verify", json={"id": "x"})


# ---------------------------------------------------------------------------
# Signed out
# ---------------------------------------------------------------------------

def test_every_endpoint_needs_a_session(app):
    client = app.test_client()

    assert client.get("/api/cards").status_code == 401
    assert client.put("/api/cards/3", json={}).status_code == 401
    assert client.delete("/api/cards/3").status_code == 401


# ---------------------------------------------------------------------------
# Keeping and listing
# ---------------------------------------------------------------------------

def test_a_kept_card_comes_back(app, monkeypatch):
    client = app.test_client()
    register(client, monkeypatch)

    client.put("/api/cards/7", json={"saved_at": "2026-10-01T09:00:00+00:00"})
    listed = client.get("/api/cards").get_json()

    assert len(listed) == 1
    assert listed[0]["pattern_id"] == "7"
    assert listed[0]["saved_at"].startswith("2026-10-01")


def test_keeping_the_same_card_twice_is_one_card(app, monkeypatch):
    client = app.test_client()
    register(client, monkeypatch)

    client.put("/api/cards/7", json={"saved_at": "2026-10-01T09:00:00+00:00"})
    client.put("/api/cards/7", json={"saved_at": "2026-10-02T09:00:00+00:00"})

    with app.app_context():
        assert UserCard.query.count() == 1
        # The earlier save is the true one: that is when the reader kept it.
        assert UserCard.query.one().saved_at.isoformat().startswith("2026-10-01")


def test_a_later_open_wins(app, monkeypatch):
    client = app.test_client()
    register(client, monkeypatch)

    client.put("/api/cards/7", json={"last_opened_at": "2026-10-01T09:00:00+00:00"})
    client.put("/api/cards/7", json={"last_opened_at": "2026-10-04T09:00:00+00:00"})
    client.put("/api/cards/7", json={"last_opened_at": "2026-10-02T09:00:00+00:00"})

    assert client.get("/api/cards").get_json()[0]["last_opened_at"].startswith("2026-10-04")


def test_deleting_is_idempotent(app, monkeypatch):
    client = app.test_client()
    register(client, monkeypatch)
    client.put("/api/cards/7", json={})

    assert client.delete("/api/cards/7").status_code == 200
    # Deleting what is already gone is the two sides agreeing, not an error.
    assert client.delete("/api/cards/7").status_code == 200
    assert client.get("/api/cards").get_json() == []


# ---------------------------------------------------------------------------
# What the second device sees
# ---------------------------------------------------------------------------

def test_a_paired_device_sees_the_same_cards(app, monkeypatch):
    laptop = app.test_client()
    handle = register(laptop, monkeypatch, credential_id=b"laptop").get_json()["handle"]
    laptop.put("/api/cards/7", json={"saved_at": "2026-10-01T09:00:00+00:00"})
    laptop.put("/api/cards/9", json={"saved_at": "2026-10-02T09:00:00+00:00"})

    code = laptop.post("/api/account/pairing").get_json()["code"]
    phone = app.test_client()
    phone.post("/api/account/pairing/claim", json={"handle": handle, "code": code})
    monkeypatch.setattr(
        "app.routes.account.webauthn.verify_registration_response",
        lambda **_: SimpleNamespace(
            credential_id=b"phone", credential_public_key=b"pub", sign_count=0
        ),
    )
    phone.post("/api/account/pairing/verify", json={"id": "x"})

    assert sorted(c["pattern_id"] for c in phone.get("/api/cards").get_json()) == ["7", "9"]


def test_one_account_never_sees_another_s_cards(app, monkeypatch):
    first = app.test_client()
    register(first, monkeypatch, credential_id=b"first")
    first.put("/api/cards/7", json={})

    second = app.test_client()
    register(second, monkeypatch, credential_id=b"second")

    assert second.get("/api/cards").get_json() == []


def test_deleting_an_account_takes_its_cards(app, monkeypatch):
    client = app.test_client()
    register(client, monkeypatch)
    client.put("/api/cards/7", json={})

    client.delete("/api/account")

    with app.app_context():
        assert UserCard.query.count() == 0
