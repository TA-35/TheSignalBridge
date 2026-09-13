#!/usr/bin/env python3
"""Score one English message with the trained Iteration 1 model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from politeness_nn import load_bundle, predict_message


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("message", help="English message to score")
    parser.add_argument("--model-dir", type=Path, default=Path("models/politeness_nn_iteration1"))
    args = parser.parse_args()
    model, metadata = load_bundle(args.model_dir)
    print(json.dumps(predict_message(args.message, model, metadata), indent=2))


if __name__ == "__main__":
    main()
