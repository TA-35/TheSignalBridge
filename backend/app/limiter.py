"""Per-IP rate limiting.

The reason this exists is cost, not spam. `api.thesignalbridge.com` has no
authentication, and every POST to /api/review makes an LLM call that spends
NVIDIA credits. The website is password-gated at CloudFront, but the API is
not behind that gate - so until this, anyone who knew the hostname could
spend the project's model budget in a loop. Verified before writing this:
five unauthenticated calls in a row, all 200, no throttling.

WHOSE ADDRESS IS COUNTED

nginx terminates TLS on the same box and proxies to gunicorn on
127.0.0.1:8000, so `request.remote_addr` is the loopback address for every
request. Keying on it unmodified would count all users as one client and
throttle the whole site to a single IP's budget - an outage caused by the
protection.

ProxyFix (installed in create_app) fixes that. nginx builds the header with
`$proxy_add_x_forwarded_for`, which APPENDS the real peer address to whatever
the client sent, so a client that forges `X-Forwarded-For: 1.2.3.4` produces
`1.2.3.4, <their real IP>`. ProxyFix with x_for=1 reads the rightmost entry -
the one nginx added - so the forged prefix is ignored. Trusting the leftmost
entry, which is what "just read X-Forwarded-For" usually means, would let any
caller pick a fresh identity per request and skip the limit entirely.

THE LIMITS ARE A CEILING, NOT A PRECISE NUMBER

Storage is in-process, and the unit runs `gunicorn --workers 3`. Each worker
keeps its own counter, so a single client spread across all three can reach
roughly 3x the configured rate before being throttled. The numbers below are
chosen so that 3x is still an acceptable ceiling on spend rather than pretending
the multiplication is not there.

Making it exact needs storage shared between workers - the Postgres instance
this app already has, or Redis. That is the upgrade path if the limits ever
need to be tight rather than merely bounded; it is deliberately not done here,
because a bounded cost was the whole problem and a DB write per request is a
real price to pay for precision nobody needs yet.
"""
from __future__ import annotations

import os

from flask import jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Built here and initialised in create_app, the same shape as `db` and
# `migrate`, so tests can import it without standing up an app.
limiter = Limiter(
    key_func=get_remote_address,
    # Applied to every route that does not name its own. Generous, because
    # its job is to catch a runaway loop rather than to shape normal use.
    default_limits=["300 per hour"],
    # Silent by default. An unreachable shared store must not take the API
    # down with it, and in-memory storage cannot fail this way anyway - this
    # is here so that switching to Redis later cannot turn a cache outage
    # into a site outage.
    storage_uri="memory://",
    strategy="fixed-window",
)


def register_rate_limiting(app) -> None:
    """Attach the limiter and give 429 the same JSON shape as every error."""
    # Read the environment HERE, not in the Config class body. A class body
    # executes once when the module is first imported, which is before any
    # test has had a chance to set the variable - so the value would be
    # whatever the first import saw, for the life of the process. Reading it
    # per app build means create_app() actually reflects the environment it
    # was called in.
    #
    # It has to be decided before init_app either way: flask-limiter only
    # builds its storage when limiting is enabled at init, so flipping the
    # flag on the app afterwards leaves a limiter with nowhere to count.
    enabled = os.environ.get("RATELIMIT_ENABLED", "true").strip().lower()
    app.config["RATELIMIT_ENABLED"] = enabled not in {"0", "false", "no", "off"}

    limiter.init_app(app)

    @app.errorhandler(429)
    def _too_many_requests(exc):
        # Werkzeug's default 429 body is HTML. Every other endpoint answers
        # {"error": ...}, and the frontend reads that key.
        retry_after = getattr(exc, "retry_after", None) or getattr(
            getattr(exc, "description", None), "retry_after", None
        )
        body = {"error": "Too many requests. Please wait a moment and try again."}
        response = jsonify(body)
        response.status_code = 429
        if retry_after:
            response.headers["Retry-After"] = str(retry_after)
        return response
