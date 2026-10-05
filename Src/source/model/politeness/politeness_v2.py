#!/usr/bin/env python3
"""Iteration 2 politeness scorer: NumPy-only inference for the distilled text CNN.

The network was trained offline (see train_student.py) to imitate a fine-tuned RoBERTa
teacher. At run time it needs nothing but NumPy and the files in the model directory.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

TOKEN_RE = re.compile(r"<url>|[a-z]+(?:'[a-z]+)?|[0-9]+|[!?.,:;@()\-]", re.IGNORECASE)
PAD, UNK = 0, 1
MAX_TOKENS = 96


def tokenize(text: str) -> list[str]:
    tokens = [t.lower() for t in TOKEN_RE.findall(text)]
    return ["<num>" if t[0].isdigit() else t for t in tokens][:MAX_TOKENS]


def encode(text: str, vocab: dict[str, int]) -> np.ndarray:
    ids = [vocab.get(t, UNK) for t in tokenize(text)]
    return np.array(ids or [UNK], dtype=np.int64)


class PolitenessCNN:
    """Word embeddings -> parallel 1-D convolutions (widths 1-4) -> max+mean pooling -> MLP."""

    def __init__(self, arrays: dict[str, np.ndarray], widths: list[int]):
        self.a = {k: v.astype(np.float32) for k, v in arrays.items()}
        self.widths = widths

    def score_standardized(self, ids: np.ndarray) -> float:
        a = self.a
        pad = max(self.widths) - 1
        x = a["emb"][np.concatenate([np.zeros(pad, np.int64), ids, np.zeros(pad, np.int64)])]  # (T, E)
        pooled = []
        for k in self.widths:
            W, b = a[f"conv{k}_w"], a[f"conv{k}_b"]            # W: (F, k*E)
            T = x.shape[0] - k + 1
            windows = np.concatenate([x[i:i + T] for i in range(k)], axis=1)  # (T, k*E)
            h = np.maximum(windows @ W.T + b, 0.0)
            pooled += [h.max(axis=0), h.mean(axis=0)]
        z = np.concatenate(pooled)
        h = np.tanh(z @ a["fc1_w"].T + a["fc1_b"])
        return float(h @ a["fc2_w"].T.ravel() + a["fc2_b"].ravel()[0])


def load_bundle(model_dir: Path):
    meta = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    vocab = json.loads((model_dir / "vocab.json").read_text(encoding="utf-8"))
    arrays = dict(np.load(model_dir / "politeness_cnn.npz"))
    return PolitenessCNN(arrays, meta["model"]["conv_widths"]), vocab, meta


def predict_message(message: str, model: PolitenessCNN, vocab: dict, meta: dict) -> dict:
    ids = encode(message, vocab)
    s = model.score_standardized(ids)
    score = s * meta["target"]["train_std"] + meta["target"]["train_mean"]
    low, high = meta["levels"]["prediction_cutoffs"]
    level = "low" if score < low else "medium" if score < high else "high"
    words = re.findall(r"[a-z]+(?:'[a-z]+)?", message.lower())
    warnings = []
    if len(words) < 5 or len(message.strip()) < 20:
        warnings.append("short_input")
    if not words:
        warnings.append("no_english_words")
    if np.mean(ids == UNK) > 0.4:
        warnings.append("mostly_unknown_words")
    return {"score": round(score, 4), "level": level, "warnings": warnings}
