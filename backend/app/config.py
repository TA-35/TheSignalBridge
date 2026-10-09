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


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CORS_ORIGINS = _split_env_list("CORS_ORIGINS")

    # Rate limiting, on by default. Deliberately NOT read here: a class body
    # runs once at import, so the value would be frozen before any test could
    # change it - the same trap that bit PipelineConfig's dataclass defaults.
    # register_rate_limiting() reads the environment when the app is built.
    # See app/limiter.py.

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
    # 90s, not 30. The reading prompt asks the model to interpret rather than
    # restate, which roughly doubled generation time - measured 15-30s per
    # call, so a 30s proxy timeout cut off the slower half and returned
    # degraded output for a response that was on its way.
    #
    # Must stay above PIPELINE_LLM_TIMEOUT on the inference host, so the model
    # call is what gives up first. When the proxy times out instead, the
    # inference service carries on generating a response nobody will read.
    INFERENCE_TIMEOUT = float(os.environ.get("INFERENCE_TIMEOUT", "90"))
    # /api/compose: up to two model calls (one retry if the grounding check
    # rejects the first rewrite), each capped by COMPOSE_LLM_TIMEOUT (45s) on
    # the inference host. Must stay above twice that, for the same reason as
    # above. Whatever proxies to this API needs a read timeout above it too.
    COMPOSE_TIMEOUT = float(os.environ.get("COMPOSE_TIMEOUT", "100"))

    # --- Accounts -------------------------------------------------------
    # The session cookie. The site and the API are different hosts under one
    # registrable domain (thesignalbridge.com and api.thesignalbridge.com),
    # so the cookie is set on the parent domain and SameSite=Lax is enough -
    # they are same-site even though they are cross-origin. Keeping the
    # session in an HttpOnly cookie rather than a token in localStorage is
    # the point: script on the page cannot read it.
    SESSION_COOKIE_NAME = "bw_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # A Secure cookie is dropped by the browser over plain http, which is
    # what local dev runs on - hence the switch, defaulting to the safe side.
    SESSION_COOKIE_SECURE = _flag("SESSION_COOKIE_SECURE", True)
    # Unset locally (the host is localhost); ".thesignalbridge.com" in prod.
    SESSION_COOKIE_DOMAIN = os.environ.get("SESSION_COOKIE_DOMAIN") or None

    # WebAuthn. The relying party is the registrable domain, so one passkey
    # works on the site and against the API. The browser checks these, so a
    # wrong value here fails every registration with a vague error - see
    # docs/accounts.md.
    WEBAUTHN_RP_ID = os.environ.get("WEBAUTHN_RP_ID", "localhost")
    WEBAUTHN_RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "BetweenWords")
    # Every origin the page may be served from. Checked against the origin
    # the authenticator signed, so it cannot be inferred from the request.
    WEBAUTHN_ORIGINS = _split_env_list("WEBAUTHN_ORIGINS") or [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
