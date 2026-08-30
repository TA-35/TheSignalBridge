from flask import Blueprint, jsonify

from ..models.pattern import Pattern

bp = Blueprint("patterns", __name__)


@bp.get("")
def list_patterns():
    patterns = Pattern.query.all()
    return jsonify([p.to_dict() for p in patterns])
