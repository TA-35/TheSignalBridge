from .decode import bp as decode_bp
from .patterns import bp as patterns_bp


def register_blueprints(app):
    app.register_blueprint(decode_bp, url_prefix="/api/decode")
    app.register_blueprint(patterns_bp, url_prefix="/api/patterns")
