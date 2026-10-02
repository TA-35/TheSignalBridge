"""Stopgap: produce the Circa weights the adapter needs.

Src/source/model/circa/circa_nn.py trains a classifier and prints its score,
but never saves anything, so there is no artifact for the pipeline to load.
Constraint 4 says that directory belongs to a teammate and must not be
modified, so this script reproduces its exact configuration here instead and
writes the fitted objects to disk.

Everything below is copied from circa_nn.py deliberately - same vectorizer
settings, same MLP hyperparameters, same seed, same validation-tuned
threshold. Test indirect F1 reproduces at 0.610. Do not "improve" it here;
if it drifts from circa_nn.py the adapter stops representing Anuvrat's model.

Delete this once Anuvrat ships his own saved weights and predict().

    python Src/source/pipeline/train_circa_weights.py
"""
from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import f1_score, precision_recall_curve
from sklearn.neural_network import MLPClassifier

SPLIT = Path("data/staging/circa_model_split.parquet")
SEED = 2002  # circa_nn.py's seed - keep identical


VARIANTS = {
    # circa_nn.py. Deployable today: the only input is the pasted message.
    "answer_only": {
        "build": lambda d: d["answer-Y"].astype(str),
        "sublinear": False,
        "dir": "circa_nn_iteration1",
        "expected_f1": 0.610,
    },
    # circa_nn_v2.py. Scores higher (0.647) but only when a real question is
    # supplied. Measured: served with a blank question it drops to 0.590,
    # below answer-only. Kept here so it is ready the day a flow collects one.
    "question_answer": {
        "build": lambda d: "Q: " + d["question-X"].astype(str)
                           + " A: " + d["answer-Y"].astype(str),
        "sublinear": True,
        "dir": "circa_nn_v2_iteration1",
        "expected_f1": 0.647,
    },
}


def main(variant: str = "answer_only") -> None:
    if not SPLIT.exists():
        raise SystemExit(
            f"{SPLIT} not found. Rebuild it first:\n"
            "  python Src/source/clean/clean_circa.py\n"
            "  python Src/source/model/circa/circa_baseline.py"
        )

    df = pd.read_parquet(SPLIT)
    train, val, test = (df[df["split"] == s] for s in ("train", "val", "test"))
    print(f"train {len(train):,} | val {len(val):,} | test {len(test):,}")

    build = VARIANTS[variant]["build"]
    sublinear = VARIANTS[variant]["sublinear"]
    vec = TfidfVectorizer(min_df=2, ngram_range=(1, 2), sublinear_tf=sublinear)
    Xtr = vec.fit_transform(build(train))
    Xvl = vec.transform(build(val))
    Xte = vec.transform(build(test))
    print(f"[{variant}] features: {Xtr.shape[1]:,} TF-IDF terms")

    clf = MLPClassifier(
        hidden_layer_sizes=(128,), activation="relu", early_stopping=True,
        n_iter_no_change=8, max_iter=200, random_state=SEED,
    )
    clf.fit(Xtr, train["label"].values)

    # Threshold tuned on validation only, never on test.
    vs = clf.predict_proba(Xvl)[:, 1]
    prec, rec, thr = precision_recall_curve(val["label"].values, vs)
    f1s = 2 * prec * rec / (prec + rec + 1e-9)
    best = int(np.argmax(f1s))
    threshold = float(thr[best]) if best < len(thr) else 0.5

    ts = clf.predict_proba(Xte)[:, 1]
    test_f1 = float(f1_score(test["label"].values, (ts >= threshold).astype(int)))
    print(f"threshold {threshold:.3f} | test indirect F1 {test_f1:.3f} "
          f"(expected {VARIANTS[variant]['expected_f1']})")

    OUT_DIR = Path("models") / VARIANTS[variant]["dir"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"vectorizer": vec, "classifier": clf}, OUT_DIR / "circa_tfidf_mlp.joblib")
    (OUT_DIR / "metadata.json").write_text(json.dumps({
        "model": "circa",
        "source": f"reproduced from Src/source/model/circa/{'circa_nn.py' if variant == 'answer_only' else 'circa_nn_v2.py'}",
        "variant": variant,
        "input": VARIANTS[variant]["build"].__doc__ or variant,
        "labels": {"0": "direct", "1": "indirect"},
        "threshold": threshold,
        "seed": SEED,
        "features": int(Xtr.shape[1]),
        "test_indirect_f1": round(test_f1, 4),
        "split_rows": {"train": len(train), "val": len(val), "test": len(test)},
        "caveat": "trained on casual social language (Circa), not workplace email",
    }, indent=2) + "\n")
    print(f"saved -> {OUT_DIR}")


if __name__ == "__main__":
    import sys
    for name in (sys.argv[1:] or list(VARIANTS)):
        main(name)
