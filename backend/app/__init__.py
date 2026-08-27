from flask import Flask
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

    db.init_app(app)
    migrate.init_app(app, db)

    from .routes import register_blueprints
    register_blueprints(app)

    return app
