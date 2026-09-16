from app import create_app
from app.config import Config
import pytest
from sqlalchemy.exc import ArgumentError


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


def test_decode_rejects_empty_message():
    app = create_app(TestConfig)
    client = app.test_client()

    response = client.post("/api/decode", json={"message": "  "})

    assert response.status_code == 400


def test_create_app_starts_without_a_database_url(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-only")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    app = create_app()

    assert app.test_client().post("/api/review", json={"message": "Send it by Friday."}).status_code == 200


def test_create_app_still_rejects_an_explicitly_invalid_database_url(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-only")

    with pytest.raises(ArgumentError):
        class InvalidDbConfig(Config):
            SQLALCHEMY_DATABASE_URI = ""

        create_app(InvalidDbConfig)
