"""Tone adapter - wraps Src/source/model/tone/enron_register.py.

Final build classifier: neutral / casual / formal. Informal is merged into
casual and terse is dropped. It's a DistilBERT model trained on 35k Enron
emails that were auto-labelled with Claude. The weights live in
models/enron_register_distilbert/ (too big for git, shared on Drive under
Iteration Build > Models).

Held-out results (10% split, scored against the Claude labels, not human
ones): accuracy 0.80, macro F1 0.78. Precision per class: neutral 0.89,
casual 0.84, formal 0.58. Casual is fine now (recall 0.85, the old model
was 0.30), so the old casual cap is gone. Formal is the label the model
over-uses - it sometimes calls plain neutral emails formal - so formal
gets its confidence capped instead, same idea as before.

Never raises: missing torch, missing weights or any runtime error comes
back as the unavailable stub.
"""

from typing import Any

from ..contract import unavailable, validate
from ._paths import WEIGHTS_DIR, add_model_dir

MODEL_NAME = "tone"
MODEL_PATH = WEIGHTS_DIR / "enron_register_distilbert"

# formal precision is 0.58 on the held-out set, so don't let it sound sure
_UNRELIABLE_CLASSES = {"formal"}
_UNRELIABLE_CAP = 0.6


def predict(text: str) -> dict[str, Any]:
    """Tone comment on `text`, in the contract shape."""
    try:
        add_model_dir("tone")
        import enron_register  # noqa: E402

        # the script uses a cwd-relative path, point it at the repo copy instead
        enron_register.MODEL_DIR = MODEL_PATH
        out = enron_register.classify(text)

        label = out["tone"]
        confidence = float(out["tone_scores"][label])
        note = f"register reads as {label}"

        if label in _UNRELIABLE_CLASSES and confidence > _UNRELIABLE_CAP:
            reported = confidence
            confidence = _UNRELIABLE_CAP
            note += (
                f"; confidence capped from {reported:.2f} to {confidence:.2f} - "
                f"'{label}' precision is 0.58 on the held-out set, it sometimes "
                f"fires on neutral emails"
            )

        return validate({
            "model": MODEL_NAME,
            "label": label,
            "confidence": confidence,
            "note": note,
        })
    except Exception as exc:  # noqa: BLE001 - deliberate: never propagate
        return unavailable(MODEL_NAME, type(exc).__name__)
