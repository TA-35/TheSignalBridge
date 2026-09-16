import os

from dotenv import load_dotenv

# Loads backend/.env for local dev, regardless of entry point (flask run,
# wsgi.py, gunicorn). Never overrides a real env var that's already set, so
# this is a no-op in production, where systemd supplies the environment
# directly (see infra/systemd/backend.service).
load_dotenv()


def _split_env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"{name} is not set. Copy backend/.env.example to backend/.env "
            f"and fill in a real value - see that file for how to generate one."
        )
    return value


class Config:
    # No insecure fallback here on purpose - a Flask app run with a known
    # SECRET_KEY (this used to default to the literal "dev") lets anyone who
    # has read this file's history forge session cookies and CSRF tokens.
    # Fail to start instead of running unsafely.
    SECRET_KEY = _require_env("SECRET_KEY")

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CORS_ORIGINS = _split_env_list("CORS_ORIGINS")

    # Backstop against oversized request bodies in general, on top of the
    # /api/decode route's own message-length check - this one rejects the
    # request before Flask even reads/parses the body. 100 KB comfortably
    # covers the largest legitimate payload (a ~5000-character message,
    # worst-case UTF-8, plus JSON overhead) with room to spare.
    MAX_CONTENT_LENGTH = 100_000

    # Where the pipeline inference service listens. Empty means the feature
    # is off: /api/review returns a degraded response and everything else
    # carries on exactly as before. That default matters - a deploy that has
    # not been given this value must not break the site.
    INFERENCE_URL = os.environ.get("INFERENCE_URL", "")
    # Stage one is local work only, so a short timeout is right; stage two
    # waits on a model and needs room.
    INFERENCE_QUICK_TIMEOUT = float(os.environ.get("INFERENCE_QUICK_TIMEOUT", "5"))
    INFERENCE_TIMEOUT = float(os.environ.get("INFERENCE_TIMEOUT", "30"))
