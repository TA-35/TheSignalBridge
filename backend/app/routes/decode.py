from flask import Blueprint, jsonify, request

from ..services import ai_decoder

bp = Blueprint("decode", __name__)


@bp.post("")
def decode_message():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")

    try:
        result = ai_decoder.decode(message)
    except ValueError as exc:
        # Empty or meaningless input - contract says 400, not a breakdown.
        return jsonify({"error": str(exc)}), 400

    return jsonify(result)
