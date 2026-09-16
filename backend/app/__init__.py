from flask import Flask, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

from .config import Config

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    CORS(app, origins=app.config.get("CORS_ORIGINS", []))

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
