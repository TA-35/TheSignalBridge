import os

# Config.SECRET_KEY now raises if unset (see app/config.py) - tests and CI
# have no real .env file, so give them a harmless placeholder before any
# test module imports app.config. setdefault so a real value (e.g. a
# developer's local .env) always wins.
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
