"""Progress-dashboard data that follows an account between devices.

What matters: a second device signing in sees the same days, minutes and
reviews; replaying the same data never double counts; free text never
travels; and a signed-out caller gets nowhere.
"""
from types import SimpleNamespace

import pytest

from app import create_app, db
from app.config import Config
from app.models.user_progress import UserActivity, UserPhraseEvent


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


LAPTOP = "laptop-0001"
PHONE = "phone-00002"


def body(device=LAPTOP, activity=(), events=()):
    return {"device_id": device, "activity": list(activity), "phrase_events": list(events)}


def act(date, feature, minutes=0):
    return {"date": date, "feature": feature, "minutes": minutes}


def ev(pattern_id, kind, date):
    return {"pattern_id": pattern_id, "kind": kind, "date": date}


# ---------------------------------------------------------------------------
# Signed out
# ---------------------------------------------------------------------------

def test_every_endpoint_needs_a_session(app):
    client = app.test_client()

    assert client.get("/api/progress").status_code == 401
    assert client.put("/api/progress", json=body()).status_code == 401
    assert client.delete("/api/progress").status_code == 401


# ---------------------------------------------------------------------------
# Storing and replaying
# ---------------------------------------------------------------------------

def test_stored_progress_comes_back(app, monkeypatch):
    client = app.test_client()
    register(client, monkeypatch)

    client.put("/api/progress", json=body(
        activity=[act("2026-10-09", "opened"), act("2026-10-09", "decoder", 12)],
        events=[ev("7", "viewed", "2026-10-09"), ev("7", "reviewed", "2026-10-10")],
    ))
    got = client.get("/api/progress").get_json()

    assert sorted((a["date"], a["feature"], a["minutes"]) for a in got["activity"]) == [
        ("2026-10-09", "decoder", 12),
        ("2026-10-09", "opened", 0),
    ]
    assert sorted((e["pattern_id"], e["kind"]) for e in got["phrase_events"]) == [
        ("7", "reviewed"),
        ("7", "viewed"),
    ]


def test_replaying_the_same_data_never_double_counts(app, monkeypatch):
    client = app.test_client()
    register(client, monkeypatch)
    data = body(activity=[act("2026-10-09", "study", 8)], events=[ev("7", "reviewed", "2026-10-09")])

    client.put("/api/progress", json=data)
    client.put("/api/progress", json=data)

    with app.app_context():
        assert UserActivity.query.count() == 1
        assert UserActivity.query.one().minutes == 8
        assert UserPhraseEvent.query.count() == 1


def test_a_device_s_minutes_only_go_up(app, monkeypatch):
    # A browser's total for a day only grows, so an older, smaller number
    # arriving late (a slow request, a stale tab) must not shrink it.
    client = app.test_client()
    register(client, monkeypatch)

    client.put("/api/progress", json=body(activity=[act("2026-10-09", "decoder", 20)]))
    client.put("/api/progress", json=body(activity=[act("2026-10-09", "decoder", 5)]))

    assert client.get("/api/progress").get_json()["activity"][0]["minutes"] == 20


def test_two_devices_on_the_same_day_are_kept_apart(app, monkeypatch):
    # Kept per device, so the dashboard can add them up without double
    # counting a device's own replay.
    client = app.test_client()
    register(client, monkeypatch)

    client.put("/api/progress", json=body(LAPTOP, activity=[act("2026-10-09", "decoder", 10)]))
    client.put("/api/progress", json=body(PHONE, activity=[act("2026-10-09", "decoder", 4)]))

    rows = client.get("/api/progress").get_json()["activity"]
    assert sorted((r["device_id"], r["minutes"]) for r in rows) == [(LAPTOP, 10), (PHONE, 4)]


# ---------------------------------------------------------------------------
# What is refused
# ---------------------------------------------------------------------------

def test_bad_rows_are_skipped_not_fatal(app, monkeypatch):
    client = app.test_client()
    register(client, monkeypatch)

    res = client.put("/api/progress", json=body(
        activity=[
            act("2026-10-09", "decoder", 5),     # fine
            act("2026-02-30", "decoder", 5),     # not a real day
            act("2026-10-09", "games", 5),       # not a feature
            act("2026-10-09", "study", -3),      # negative
            act("2026-10-09", "study", 99999),   # more than a day
            act("2026-10-09", "study", True),    # not a number
        ],
        events=[ev("7", "viewed", "2026-10-09"), ev("7", "liked", "2026-10-09"), ev("x" * 41, "viewed", "2026-10-09")],
    ))

    assert res.status_code == 200
    assert res.get_json()["skipped"] == 7
    assert len(res.get_json()["activity"]) == 1
    assert len(res.get_json()["phrase_events"]) == 1


def test_free_text_has_nowhere_to_go(app, monkeypatch):
    # The timer's "what are you working on?" stays in the browser. Even if a
    # client sent it, there is no column for it and it doesn't come back.
    client = app.test_client()
    register(client, monkeypatch)

    client.put("/api/progress", json=body(activity=[{**act("2026-10-09", "decoder", 5), "intent": "email to my manager"}]))

    assert "email to my manager" not in client.get("/api/progress").get_data(as_text=True)


def test_a_device_id_is_required(app, monkeypatch):
    client = app.test_client()
    register(client, monkeypatch)

    assert client.put("/api/progress", json={"activity": []}).status_code == 400
    assert client.put("/api/progress", json=body(device="no spaces allowed")).status_code == 400
    assert client.put("/api/progress", json=[1, 2]).status_code == 400


def test_too_much_in_one_request_is_refused(app, monkeypatch):
    client = app.test_client()
    register(client, monkeypatch)

    big = [act("2026-10-09", "decoder", 1)] * 2001
    assert client.put("/api/progress", json=body(activity=big)).status_code == 413


# ---------------------------------------------------------------------------
# Across devices and accounts
# ---------------------------------------------------------------------------

def test_a_paired_device_sees_the_same_progress(app, monkeypatch):
    laptop = app.test_client()
    handle = register(laptop, monkeypatch, credential_id=b"laptop").get_json()["handle"]
    laptop.put("/api/progress", json=body(LAPTOP, activity=[act("2026-10-01", "opened"), act("2026-10-02", "opened")]))

    code = laptop.post("/api/account/pairing").get_json()["code"]
    phone = app.test_client()
    phone.post("/api/account/pairing/claim", json={"handle": handle, "code": code})
    monkeypatch.setattr(
        "app.routes.account.webauthn.verify_registration_response",
        lambda **_: SimpleNamespace(credential_id=b"phone", credential_public_key=b"pub", sign_count=0),
    )
    phone.post("/api/account/pairing/verify", json={"id": "x"})

    days = sorted(a["date"] for a in phone.get("/api/progress").get_json()["activity"])
    assert days == ["2026-10-01", "2026-10-02"]


def test_one_account_never_sees_another_s_progress(app, monkeypatch):
    first = app.test_client()
    register(first, monkeypatch, credential_id=b"first")
    first.put("/api/progress", json=body(activity=[act("2026-10-09", "opened")]))

    second = app.test_client()
    register(second, monkeypatch, credential_id=b"second")

    assert second.get("/api/progress").get_json() == {"activity": [], "phrase_events": []}


def test_clearing_progress_removes_it_all(app, monkeypatch):
    client = app.test_client()
    register(client, monkeypatch)
    client.put("/api/progress", json=body(activity=[act("2026-10-09", "opened")], events=[ev("7", "viewed", "2026-10-09")]))

    assert client.delete("/api/progress").status_code == 200
    assert client.get("/api/progress").get_json() == {"activity": [], "phrase_events": []}


def test_deleting_an_account_takes_its_progress(app, monkeypatch):
    client = app.test_client()
    register(client, monkeypatch)
    client.put("/api/progress", json=body(activity=[act("2026-10-09", "opened")], events=[ev("7", "viewed", "2026-10-09")]))

    client.delete("/api/account")

    with app.app_context():
        assert UserActivity.query.count() == 0
        assert UserPhraseEvent.query.count() == 0
