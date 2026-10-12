"""👍/👎 on a Compose rewrite.

What matters: a vote and its reasons are stored with the model's name; nothing
else is ever stored - a field that could carry the message is refused, not
dropped quietly; and the summary adds the votes up per model.
"""
import pytest

from app import create_app, db
from app.config import Config
from app.models.compose_feedback import ComposeFeedback

MODEL = "qwen3.5-4b-ft-run2"


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


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


def rate(client, **fields):
    body = {"vote": "up", "model": MODEL} | fields
    return client.post("/api/compose/feedback", json=body)


def test_a_thumbs_up_is_stored_with_the_model(client):
    response = rate(client)
    assert response.status_code == 201
    row = ComposeFeedback.query.one()
    assert (row.vote, row.model, row.reasons, row.kept_as_written, row.after_card) == ("up", MODEL, "", False, False)
    assert row.created_at is not None


def test_a_thumbs_down_keeps_its_reasons_in_a_fixed_order_without_repeats(client):
    response = rate(client, vote="down", reasons=["too_blunt", "changed_meaning", "too_blunt"], after_card=True)
    assert response.status_code == 201
    row = ComposeFeedback.query.one()
    assert (row.vote, row.reasons, row.after_card) == ("down", "changed_meaning,too_blunt", True)


@pytest.mark.parametrize("body", [
    {"vote": "up", "model": MODEL, "message": "Can you send me the Q3 deck by Friday?"},
    {"vote": "up", "model": MODEL, "rewrite": "Could you send me the Q3 deck by Friday?"},
    {"vote": "down", "model": MODEL, "comment": "it dropped the deadline"},
])
def test_text_is_refused_not_stored(client, body):
    response = client.post("/api/compose/feedback", json=body)
    assert response.status_code == 400
    # The refusal doesn't repeat what was sent either.
    assert "Q3" not in response.get_data(as_text=True)
    assert ComposeFeedback.query.count() == 0


@pytest.mark.parametrize("fields", [
    {"vote": "sideways"},
    {"vote": None},
    {"reasons": ["it dropped the deadline"]},
    {"reasons": "too_blunt"},
    {"model": "has spaces in it"},
    {"model": "x" * 65},
    {"model": None},
    {"after_card": "yes"},
    {"kept_as_written": 1},
])
def test_anything_malformed_is_refused(client, fields):
    assert rate(client, **fields).status_code == 400
    assert ComposeFeedback.query.count() == 0


def test_not_json_is_refused(client):
    response = client.post("/api/compose/feedback", data="up", content_type="text/plain")
    assert response.status_code == 400


def test_the_summary_adds_votes_up_per_model(client):
    rate(client)
    rate(client, after_card=True)
    rate(client, vote="down", reasons=["still_unclear", "too_blunt"])
    rate(client, vote="down", reasons=["needed_rewrite"], kept_as_written=True)
    rate(client, model="qwen3.5-4b-base")

    models = client.get("/api/compose/feedback/summary").get_json()["models"]
    assert [m["model"] for m in models] == [MODEL, "qwen3.5-4b-base"]
    run2 = models[0]
    assert (run2["ratings"], run2["up"], run2["down"], run2["helpful_rate"]) == (4, 2, 2, 0.5)
    assert run2["reasons"] == {"still_unclear": 1, "too_blunt": 1, "needed_rewrite": 1}
    assert run2["kept_as_written"] == {"up": 0, "down": 1}
    assert run2["after_card"] == {"up": 1, "down": 0}
    assert models[1]["helpful_rate"] == 1.0


def test_the_summary_is_empty_before_any_rating(client):
    assert client.get("/api/compose/feedback/summary").get_json() == {"models": []}
