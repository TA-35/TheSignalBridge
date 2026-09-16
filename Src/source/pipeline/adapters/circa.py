"""Circa adapter - wraps Src/source/model/circa/.

circa_nn.py and circa_nn_v2.py both train and print a score but neither saves
a model or exposes predict(), so the missing predict() lives here.
Constraint 4 keeps that directory untouched; train_circa_weights.py
reproduces both configurations and writes the fitted objects to models/.

Two variants, and which one runs depends on whether a question is available:

    circa_nn.py     answer-only            F1 0.610
    circa_nn_v2.py  question + answer      F1 0.647

v2 is the better model and this adapter uses it whenever a question is passed
in. It is not the default, because of a third measurement: v2 trained on
"Q: <text> A: <text>" and then served "Q:  A: <text>" - which is all the
current Review and Form flows can build, since neither collects the message
being replied to - scores **0.590**, below answer-only's 0.610. The gain is
entirely in the question (sublinear_tf, v2's other change, is worth -0.002 on
its own), so without a real question v2 is a regression, not an upgrade.

So: pass a question and you get v2 and its 0.647. Pass none and you get the
model that is actually better on the input available. The day a flow starts
collecting "what are you replying to?", this switches over on its own with no
code change.

`confidence` is the predicted probability of the reported class, capped: both
variants were trained on casual social question-answer pairs, so on workplace
email they are out of domain and overconfident.
"""
from __future__ import annotations

import json
from typing import Any

from .._lazy import LazyDict
from ..contract import unavailable, validate
from ._paths import WEIGHTS_DIR

MODEL_NAME = "circa"

VARIANTS = {
    "answer_only": {
        "dir": WEIGHTS_DIR / "circa_nn_iteration1",
        "f1": 0.610,
        "source": "circa_nn.py",
    },
    "question_answer": {
        "dir": WEIGHTS_DIR / "circa_nn_v2_iteration1",
        "f1": 0.647,
        "source": "circa_nn_v2.py",
    },
}

_LABELS = {0: "direct", 1: "indirect"}

# Out-of-domain ceiling. Circa is casual social language; every message this
# pipeline sees is workplace email, so its probabilities are not taken at
# face value.
_OUT_OF_DOMAIN_CAP = 0.6

_DOMAIN_CAVEAT = (
    "trained on casual social question-answer pairs (Circa), not workplace email"
)




def _bundle_file(variant: str):
    return VARIANTS[variant]["dir"] / "circa_tfidf_mlp.joblib"


def _load_variant(variant: str) -> tuple[Any, Any, float]:
    import joblib  # noqa: E402 - lazy, so a missing sklearn stubs cleanly

    bundle = joblib.load(_bundle_file(variant))
    threshold = 0.5
    metadata_file = VARIANTS[variant]["dir"] / "metadata.json"
    if metadata_file.exists():
        threshold = float(json.loads(metadata_file.read_text())["threshold"])
    return bundle["vectorizer"], bundle["classifier"], threshold


# One load per variant, even under concurrent first calls.
_cache: LazyDict[tuple[Any, Any, float]] = LazyDict(_load_variant)


def _load(variant: str) -> tuple[Any, Any, float]:
    """Load vectorizer, classifier and tuned threshold for one variant, once."""
    return _cache.get(variant)


def _choose_variant(question: str | None) -> str:
    """v2 when there is a real question to give it, answer-only otherwise."""
    if question and question.strip():
        return "question_answer"
    return "answer_only"


def predict(text: str, question: str | None = None) -> dict[str, Any]:
    """Directness comment on `text`, in the contract shape.

    `question` is the message being replied to, when the caller has one. Supply
    it and the stronger v2 model is used; omit it and the answer-only model
    runs, which is the better of the two on that input.

    Never raises: absent weights or any runtime error degrade to the
    unavailable stub.
    """
    try:
        variant = _choose_variant(question)
        if not _bundle_file(variant).exists():
            return unavailable(MODEL_NAME, "no saved weights")

        vectorizer, classifier, threshold = _load(variant)
        body = text if text.strip() else " "
        if variant == "question_answer":
            body = f"Q: {question.strip()} A: {body}"

        p_indirect = float(classifier.predict_proba(vectorizer.transform([body]))[0, 1])
        is_indirect = p_indirect >= threshold
        label = _LABELS[int(is_indirect)]
        # Probability of the class actually reported, not always class 1.
        reported = p_indirect if is_indirect else 1.0 - p_indirect
        confidence = min(reported, _OUT_OF_DOMAIN_CAP)

        spec = VARIANTS[variant]
        note = (
            f"p(indirect)={p_indirect:.2f} against a validation-tuned threshold "
            f"of {threshold:.2f}; {spec['source']} variant '{variant}', "
            f"in-domain indirect F1 {spec['f1']}; {_DOMAIN_CAVEAT}; confidence "
            f"capped at {_OUT_OF_DOMAIN_CAP} as out of domain"
        )
        return validate({
            "model": MODEL_NAME,
            "label": label,
            "confidence": confidence,
            "note": note,
        })
    except Exception as exc:  # noqa: BLE001 - deliberate: never propagate
        return unavailable(MODEL_NAME, type(exc).__name__)
