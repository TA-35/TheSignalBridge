#!/usr/bin/env python3
"""Score a CSV of English messages while preserving row order and exact text."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from politeness_nn import load_bundle, predict_message


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--text-column", default="body")
    parser.add_argument("--model-dir", type=Path, default=Path("models/politeness_nn_iteration1"))
    args = parser.parse_args()

    model, metadata = load_bundle(args.model_dir)
    with args.input_csv.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or args.text_column not in reader.fieldnames:
            raise ValueError(f"Input must contain a {args.text_column!r} column")
        rows = list(reader)

    output_rows = []
    blank_count = 0
    short_count = 0
    scores = []
    for row in rows:
        body = row.get(args.text_column, "")
        if body is None or not body.strip():
            blank_count += 1
            score = ""
        else:
            result = predict_message(body, model, metadata)
            score = f"{result['score']:.4f}"
            scores.append(result["score"])
            short_count += int("short_input" in result["warnings"])
        output_rows.append({"body": body, "politeness_score": score})

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["body", "politeness_score"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)

    summary = {
        "input_rows": len(rows),
        "output_rows": len(output_rows),
        "scored_rows": len(scores),
        "blank_rows": blank_count,
        "short_input_warnings": short_count,
        "score_scale": "Stanford Normalized Score (not 0-1)",
        "score_min": min(scores) if scores else None,
        "score_max": max(scores) if scores else None,
        "output": str(args.output_csv),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
