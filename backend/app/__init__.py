from flask import Flask, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .limiter import register_rate_limiting

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # nginx runs on this same box and proxies to gunicorn over the loopback,
    # so without this every request appears to come from 127.0.0.1 - which
    # makes the rate limiter count all users as one client. x_for=1 because
    # exactly one proxy is in front; it reads the rightmost X-Forwarded-For
    # entry, the one nginx appended, so a forged header cannot pick the key.
    # See app/limiter.py for why the rightmost entry is the safe one.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    CORS(app, origins=app.config.get("CORS_ORIGINS", []))
    register_rate_limiting(app)

    if app.config.get("SQLALCHEMY_DATABASE_URI") is not None:
        db.init_app(app)
        migrate.init_app(app, db)

    from .routes import register_blueprints
    register_blueprints(app)

    @app.errorhandler(413)
    def _payload_too_large(_exc):
        # Werkzeug's default 413 body is HTML - normalize it to the same
        # {"error": ...} shape every other endpoint uses.
        return jsonify({"error": "Request is too large."}), 413

    return app
