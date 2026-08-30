from flask import Blueprint, jsonify, request

bp = Blueprint("decode", __name__)


@bp.post("")
def decode_message():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")

    if not message.strip():
        return jsonify({"error": "Please enter a message"}), 400

    # TODO: call app.services.ai_decoder once the extraction contract is implemented.
    return jsonify({"error": "not implemented"}), 501
