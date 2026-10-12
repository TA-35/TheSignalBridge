from .account import bp as account_bp
from .cards import bp as cards_bp
from .compose import bp as compose_bp
from .compose_feedback import bp as compose_feedback_bp
from .decode import bp as decode_bp
from .patterns import bp as patterns_bp
from .progress import bp as progress_bp
from .review import bp as review_bp


def register_blueprints(app):
    app.register_blueprint(decode_bp, url_prefix="/api/decode")
    app.register_blueprint(patterns_bp, url_prefix="/api/patterns")
    # Additive: /api/decode and /api/patterns are unchanged.
    app.register_blueprint(review_bp, url_prefix="/api/review")
    # The rewrite direction, on the same inference service. Also additive.
    app.register_blueprint(compose_bp, url_prefix="/api/compose")
    # 👍/👎 on a rewrite: the vote and fixed reason codes, never any text -
    # see routes/compose_feedback.py.
    app.register_blueprint(compose_feedback_bp, url_prefix="/api/compose/feedback")
    # Also additive. Every route above works signed out, exactly as before.
    app.register_blueprint(account_bp, url_prefix="/api/account")
    # Library cards that follow an account between devices. Signed-in only,
    # and the browser remains the source of truth - see routes/cards.py.
    app.register_blueprint(cards_bp, url_prefix="/api/cards")
    # Progress-dashboard data, same rules as cards: signed-in only, browser is
    # the source of truth, no free text - see routes/progress.py.
    app.register_blueprint(progress_bp, url_prefix="/api/progress")
