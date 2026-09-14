#!/usr/bin/env python3
"""Small NumPy text neural network used by the Iteration 1 politeness MVP."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np


TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?|[!?.,]", re.IGNORECASE)


def normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def _hash_feature(feature: str, dimension: int) -> tuple[int, float]:
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "little")
    return value % dimension, 1.0 if value & (1 << 63) else -1.0


def vectorize_text(text: str, dimension: int) -> np.ndarray:
    """Signed feature hashing over word 1/2-grams and character 3/4-grams."""
    normalized = normalize_text(text)
    tokens = TOKEN_RE.findall(normalized)
    vector = np.zeros(dimension, dtype=np.float32)

    features = [f"w1:{token}" for token in tokens]
    features.extend(f"w2:{a}_{b}" for a, b in zip(tokens, tokens[1:]))
    compact = f" {normalized} "
    for n in (3, 4):
        features.extend(f"c{n}:{compact[i:i+n]}" for i in range(max(0, len(compact) - n + 1)))

    for feature in features:
        index, sign = _hash_feature(feature, dimension)
        vector[index] += sign

    nonzero = vector != 0
    vector[nonzero] = np.sign(vector[nonzero]) * np.log1p(np.abs(vector[nonzero]))
    norm = float(np.linalg.norm(vector))
    if norm:
        vector /= norm
    return vector


def vectorize_many(texts: list[str], dimension: int) -> np.ndarray:
    matrix = np.empty((len(texts), dimension), dtype=np.float32)
    for index, text in enumerate(texts):
        matrix[index] = vectorize_text(text, dimension)
    return matrix


class PolitenessMLP:
    """One-hidden-layer regression MLP with a linear residual connection."""

    def __init__(self, dimension: int, hidden_size: int, seed: int = 5120):
        rng = np.random.default_rng(seed)
        self.W1 = rng.normal(0, np.sqrt(2 / dimension), (dimension, hidden_size)).astype(np.float32)
        self.b1 = np.zeros(hidden_size, dtype=np.float32)
        self.W2 = rng.normal(0, np.sqrt(2 / hidden_size), hidden_size).astype(np.float32)
        self.b2 = np.float32(0)
        self.W0 = np.zeros(dimension, dtype=np.float32)

    def forward(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        hidden = np.tanh(X @ self.W1 + self.b1)
        prediction = X @ self.W0 + hidden @ self.W2 + self.b2
        return prediction, hidden

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self.forward(X)[0]

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, W1=self.W1, b1=self.b1, W2=self.W2, b2=self.b2, W0=self.W0)

    @classmethod
    def load(cls, path: Path) -> "PolitenessMLP":
        arrays = np.load(path)
        model = cls(arrays["W1"].shape[0], arrays["W1"].shape[1])
        for name in ("W1", "b1", "W2", "b2", "W0"):
            setattr(model, name, arrays[name].astype(np.float32))
        return model


def load_bundle(model_dir: Path) -> tuple[PolitenessMLP, dict]:
    metadata = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    model = PolitenessMLP.load(model_dir / "politeness_mlp.npz")
    return model, metadata


def predict_message(message: str, model: PolitenessMLP, metadata: dict) -> dict:
    dimension = int(metadata["model"]["hash_dimension"])
    x = vectorize_text(message, dimension)[None, :]
    standardized = float(model.predict(x)[0])
    score = standardized * metadata["target"]["train_std"] + metadata["target"]["train_mean"]
    low, high = metadata["target"]["tertile_thresholds"]
    level = "low" if score < low else "medium" if score < high else "high"
    words = re.findall(r"[a-z]+(?:'[a-z]+)?", message.lower())
    warnings = []
    if len(words) < 5 or len(message.strip()) < 20:
        warnings.append("short_input")
    if not words:
        warnings.append("no_english_words")
    return {"score": round(score, 4), "level": level, "warnings": warnings}
