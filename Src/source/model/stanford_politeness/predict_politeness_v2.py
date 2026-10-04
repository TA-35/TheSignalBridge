#!/usr/bin/env python3
"""Score one English message with the Iteration 2 politeness model (NumPy only)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from politeness_v2 import load_bundle, predict_message


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("message", help="English message to score")
    parser.add_argument("--model-dir", type=Path, default=Path("models/politeness_nn_iteration2"))
    args = parser.parse_args()
    model, vocab, meta = load_bundle(args.model_dir)
    print(json.dumps(predict_message(args.message, model, vocab, meta), indent=2))


if __name__ == "__main__":
    main()
