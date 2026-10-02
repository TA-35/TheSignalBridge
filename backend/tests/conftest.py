import os

# Config.SECRET_KEY now raises if unset (see app/config.py) - tests and CI
# have no real .env file, so give them a harmless placeholder before any
# test module imports app.config. setdefault so a real value (e.g. a
# developer's local .env) always wins.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")

# Rate limiting off for the suite as a whole. Many tests make dozens of calls
# from one address in under a second, and a limiter would make unrelated tests
# fail depending on execution order. test_rate_limit.py turns it back on for
# the app it builds, which is the only place the limits are the thing under
# test.
os.environ.setdefault("RATELIMIT_ENABLED", "false")
