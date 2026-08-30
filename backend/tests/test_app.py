from app import create_app
from app.config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


def test_decode_rejects_empty_message():
    app = create_app(TestConfig)
    client = app.test_client()

    response = client.post("/api/decode", json={"message": "  "})

    assert response.status_code == 400
