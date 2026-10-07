"""Seed the `patterns` table from data/Library_dataset/library_dataset.json.

Run from backend/ with the venv active:

    python scripts/seed_patterns.py

Safe to re-run - existing rows (matched by name) are left alone, only
missing ones are inserted. Reads the content team's file directly rather
than hardcoding rows here, so re-running after they revise it picks up
the changes with no code edit.
"""
import json
import os
import sys

# Load backend/.env even when this isn't run through the `flask` CLI
# (which auto-loads it; a plain `python` invocation doesn't).
from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_DIR)
sys.path.insert(0, BACKEND_DIR)

from app import create_app, db  # noqa: E402
from app.models.pattern import Pattern  # noqa: E402

DATASET_FILE = os.path.join(REPO_ROOT, "data", "library_dataset", "library_dataset.json")


def load_seed_rows() -> list[dict]:
    with open(DATASET_FILE, encoding="utf-8") as f:
        rows = json.load(f)

    # Pattern.id is the database's own auto-increment primary key - drop
    # the dataset's own `id` rather than forcing it, so re-running this
    # after the content team revises the file can't collide with rows
    # already inserted under a different numbering.
    return [
        {
            "name": row["name"],
            "category": row["category"],
            "implies": row["implies"],
            "why_misread": row["why_misread"],
        }
        for row in rows
    ]


def seed():
    app = create_app()
    with app.app_context():
        rows = load_seed_rows()
        existing_names = {p.name for p in Pattern.query.all()}
        inserted = 0
        for row in rows:
            if row["name"] in existing_names:
                continue
            db.session.add(Pattern(**row))
            inserted += 1
        db.session.commit()
        print(f"Inserted {inserted} new pattern(s), {len(rows) - inserted} already present.")


if __name__ == "__main__":
    seed()
