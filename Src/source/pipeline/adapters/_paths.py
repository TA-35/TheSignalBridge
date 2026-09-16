"""Locating the teammates' model directories without importing them as packages.

Src/source/model/* holds loose scripts, not packages - there is no __init__.py
anywhere under Src, and the scripts import their siblings by bare name
(`from politeness_nn import ...`). So an adapter reaches one by putting that
directory on sys.path, exactly as running the script directly would.

Paths are anchored to the repository root rather than the working directory.
The model scripts themselves use CWD-relative paths and only work when run
from the repo root; adapters get called from a web request, where the working
directory is whatever gunicorn happened to start in.
"""
from __future__ import annotations

import sys
from pathlib import Path

# _paths.py -> adapters -> pipeline -> source -> Src -> repo root
REPO_ROOT = Path(__file__).resolve().parents[4]

MODEL_DIR = REPO_ROOT / "Src" / "source" / "model"
WEIGHTS_DIR = REPO_ROOT / "models"


def add_model_dir(name: str) -> Path:
    """Put Src/source/model/<name> on sys.path and return it.

    Idempotent - repeated calls do not stack duplicate entries.
    """
    directory = MODEL_DIR / name
    entry = str(directory)
    if entry not in sys.path:
        sys.path.insert(0, entry)
    return directory
