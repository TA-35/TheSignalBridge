from flask import Blueprint, jsonify, request

from ..services import ai_decoder

from ..limiter import limiter

bp = Blueprint("decode", __name__)

# Kept in sync with MAX_MESSAGE_LENGTH in
# frontend/src/services/decodeService.ts - see docs/api-contract.md. A large
# message runs spaCy plus several regexes over the full string, so an
# unbounded length is a cheap denial-of-service vector, not just a UX issue.
MAX_MESSAGE_LENGTH = 5000


@bp.post("")
# Cheap - spaCy only, ~6ms, no model call. Loose enough not to
# interfere with someone decoding message after message.
@limiter.limit("30 per minute; 300 per hour")
def decode_message():
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")

    if len(message) > MAX_MESSAGE_LENGTH:
        return (
            jsonify({"error": f"Message is too long (limit is {MAX_MESSAGE_LENGTH} characters)."}),
            413,
        )

    try:
        result = ai_decoder.decode(message)
    except ValueError as exc:
        # Empty or meaningless input - contract says 400, not a breakdown.
        return jsonify({"error": str(exc)}), 400

    return jsonify(result)
