#!/usr/bin/env python3
"""Score a CSV of English messages with the Iteration 2 model, preserving row order and text."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from politeness_v2 import load_bundle, predict_message


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_csv", type=Path)
    parser.add_argument("output_csv", type=Path)
    parser.add_argument("--text-column", default="body")
    parser.add_argument("--model-dir", type=Path, default=Path("models/politeness_nn_iteration2"))
    args = parser.parse_args()

    model, vocab, meta = load_bundle(args.model_dir)
    with args.input_csv.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or args.text_column not in reader.fieldnames:
            raise ValueError(f"Input must contain a {args.text_column!r} column")
        rows = list(reader)

    output_rows, scores, blank, short = [], [], 0, 0
    for row in rows:
        body = row.get(args.text_column, "")
        if body is None or not body.strip():
            blank += 1
            output_rows.append({"body": body, "politeness_score": "", "politeness_level": ""})
            continue
        result = predict_message(body, model, vocab, meta)
        scores.append(result["score"])
        short += int("short_input" in result["warnings"])
        output_rows.append({"body": body, "politeness_score": f"{result['score']:.4f}", "politeness_level": result["level"]})

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["body", "politeness_score", "politeness_level"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(output_rows)

    print(json.dumps({
        "input_rows": len(rows), "scored_rows": len(scores), "blank_rows": blank, "short_input_warnings": short,
        "score_scale": "Stanford Normalized Score (not 0-1)",
        "score_min": min(scores) if scores else None, "score_max": max(scores) if scores else None,
        "output": str(args.output_csv),
    }, indent=2))


if __name__ == "__main__":
    main()
