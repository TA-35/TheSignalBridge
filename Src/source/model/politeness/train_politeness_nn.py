#!/usr/bin/env python3
"""Train and evaluate the Iteration 1 English politeness neural network."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path

import numpy as np

from politeness_nn import PolitenessMLP, normalize_text, vectorize_many


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        type=Path,
        default=Path("data/Stanford_Politeness/stanford_politeness_clean.csv"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("models/politeness_nn_iteration1"))
    parser.add_argument("--dimension", type=int, default=1024)
    parser.add_argument("--hidden-size", type=int, default=32)
    parser.add_argument("--epochs", type=int, default=35)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=0.003)
    parser.add_argument("--patience", type=int, default=6)
    parser.add_argument("--seed", type=int, default=5120)
    return parser.parse_args()


def load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    required = {"Request", "Normalized Score", "source", "is_high_disagreement"}
    missing = required.difference(rows[0] if rows else {})
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    return rows


def grouped_split(rows: list[dict], seed: int) -> dict[str, np.ndarray]:
    """Keep identical normalized messages together and approximately stratify labels/source."""
    groups: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(rows):
        groups[normalize_text(row["Request"])].append(index)

    labels = np.array([float(row["Normalized Score"]) for row in rows])
    q1, q2 = np.quantile(labels, [1 / 3, 2 / 3])
    strata: dict[tuple[str, int], list[list[int]]] = defaultdict(list)
    for indices in groups.values():
        mean_label = float(labels[indices].mean())
        label_bin = 0 if mean_label < q1 else 1 if mean_label < q2 else 2
        source = rows[indices[0]]["source"]
        strata[(source, label_bin)].append(indices)

    rng = np.random.default_rng(seed)
    assigned = {"train": [], "validation": [], "test": []}
    for group_list in strata.values():
        rng.shuffle(group_list)
        counts = {name: 0 for name in assigned}
        total = sum(len(group) for group in group_list)
        targets = {"train": 0.70 * total, "validation": 0.15 * total, "test": 0.15 * total}
        for group in sorted(group_list, key=len, reverse=True):
            split = min(assigned, key=lambda name: counts[name] / max(targets[name], 1))
            assigned[split].extend(group)
            counts[split] += len(group)

    return {name: np.array(sorted(indices), dtype=np.int64) for name, indices in assigned.items()}


def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    error = y_pred - y_true
    mae = float(np.mean(np.abs(error)))
    rmse = float(np.sqrt(np.mean(error**2)))
    pearson = float(np.corrcoef(y_true, y_pred)[0, 1])
    true_rank = np.argsort(np.argsort(y_true)).astype(np.float64)
    pred_rank = np.argsort(np.argsort(y_pred)).astype(np.float64)
    spearman = float(np.corrcoef(true_rank, pred_rank)[0, 1])
    return {"mae": mae, "rmse": rmse, "pearson": pearson, "spearman": spearman}


def train(model: PolitenessMLP, X: np.ndarray, y: np.ndarray, weights: np.ndarray,
          X_val: np.ndarray, y_val: np.ndarray, args: argparse.Namespace) -> tuple[PolitenessMLP, list[dict]]:
    parameters = ["W1", "b1", "W2", "b2", "W0"]
    first = {name: np.zeros_like(getattr(model, name)) for name in parameters}
    second = {name: np.zeros_like(getattr(model, name)) for name in parameters}
    rng = np.random.default_rng(args.seed)
    best = math.inf
    best_epoch = 0
    best_path = args.output_dir / ".best.npz"
    history = []
    step = 0

    for epoch in range(1, args.epochs + 1):
        order = rng.permutation(len(X))
        for start in range(0, len(X), args.batch_size):
            indices = order[start:start + args.batch_size]
            xb, yb, wb = X[indices], y[indices], weights[indices]
            pred, hidden = model.forward(xb)
            error = pred - yb
            delta = 1.0
            grad_pred = np.where(np.abs(error) <= delta, error, delta * np.sign(error))
            grad_pred = grad_pred * wb / max(float(wb.sum()), 1.0)

            grads = {
                "W2": hidden.T @ grad_pred,
                "b2": np.array(grad_pred.sum(), dtype=np.float32),
                "W0": xb.T @ grad_pred,
            }
            grad_hidden = grad_pred[:, None] * model.W2[None, :] * (1 - hidden**2)
            grads["W1"] = xb.T @ grad_hidden
            grads["b1"] = grad_hidden.sum(axis=0)

            step += 1
            for name in parameters:
                grad = np.clip(grads[name], -2.0, 2.0).astype(np.float32)
                first[name] = 0.9 * first[name] + 0.1 * grad
                second[name] = 0.999 * second[name] + 0.001 * grad**2
                m_hat = first[name] / (1 - 0.9**step)
                v_hat = second[name] / (1 - 0.999**step)
                updated = getattr(model, name) - args.learning_rate * m_hat / (np.sqrt(v_hat) + 1e-8)
                setattr(model, name, updated.astype(np.float32))

        val_prediction = model.predict(X_val)
        val_mae = float(np.mean(np.abs(val_prediction - y_val)))
        history.append({"epoch": epoch, "validation_mae_standardized": val_mae})
        print(f"epoch={epoch:02d} validation_mae_standardized={val_mae:.4f}", flush=True)
        if val_mae < best - 1e-4:
            best, best_epoch = val_mae, epoch
            model.save(best_path)
        elif epoch - best_epoch >= args.patience:
            print(f"early_stopping best_epoch={best_epoch}")
            break

    best_model = PolitenessMLP.load(best_path)
    best_path.unlink()
    return best_model, history


def main() -> None:
    args = parse_args()
    np.set_printoptions(precision=4, suppress=True)
    rows = load_rows(args.data)
    splits = grouped_split(rows, args.seed)
    split_sets = {name: set(values.tolist()) for name, values in splits.items()}
    assert not (split_sets["train"] & split_sets["validation"] or split_sets["train"] & split_sets["test"] or split_sets["validation"] & split_sets["test"])

    texts = [row["Request"] for row in rows]
    target = np.array([float(row["Normalized Score"]) for row in rows], dtype=np.float32)
    print(f"vectorizing rows={len(rows)} dimension={args.dimension}", flush=True)
    X = vectorize_many(texts, args.dimension)

    train_indices = splits["train"]
    train_mean = float(target[train_indices].mean())
    train_std = float(target[train_indices].std())
    standardized = (target - train_mean) / train_std
    weights = np.array([0.55 if row["is_high_disagreement"] == "True" else 1.0 for row in rows], dtype=np.float32)

    model = PolitenessMLP(args.dimension, args.hidden_size, args.seed)
    model, history = train(
        model,
        X[train_indices], standardized[train_indices], weights[train_indices],
        X[splits["validation"]], standardized[splits["validation"]], args,
    )

    results = {}
    predictions = {}
    for name, indices in splits.items():
        pred = model.predict(X[indices]) * train_std + train_mean
        predictions[name] = pred
        results[name] = metrics(target[indices], pred)

    q1, q2 = [float(value) for value in np.quantile(target[train_indices], [1 / 3, 2 / 3])]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    model.save(args.output_dir / "politeness_mlp.npz")
    metadata = {
        "iteration": 1,
        "task": "English request politeness regression",
        "data": {"file": args.data.name, "rows": len(rows), "split_rows": {k: len(v) for k, v in splits.items()}},
        "model": {"type": "hashed-ngram residual MLP", "hash_dimension": args.dimension, "hidden_size": args.hidden_size, "seed": args.seed},
        "target": {"name": "Normalized Score", "train_mean": train_mean, "train_std": train_std, "tertile_thresholds": [q1, q2]},
        "training": {"epochs_requested": args.epochs, "epochs_completed": len(history), "batch_size": args.batch_size, "learning_rate": args.learning_rate, "high_disagreement_weight": 0.55},
        "metrics": results,
        "history": history,
        "limitations": [
            "Trained on English requests from Wikipedia and Stack Exchange.",
            "Levels are relative to this corpus, not universal politeness categories.",
            "Iteration 1 does not generate rewrites or calibrated predictive uncertainty."
        ]
    }
    (args.output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    with (args.output_dir / "test_predictions.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["row_index", "source", "actual_score", "predicted_score"])
        for index, prediction in zip(splits["test"], predictions["test"]):
            writer.writerow([int(index), rows[index]["source"], float(target[index]), float(prediction)])

    shutil.copy2(args.data, args.output_dir / "training_data_snapshot.csv")
    print(json.dumps({"output_dir": str(args.output_dir), "metrics": results}, indent=2))


if __name__ == "__main__":
    main()
