"""Lock the gold set: record a SHA-256 for every gold file, check it before use.

The gold set is the 180 hand-checked messages every model is judged on (60
per dataset, never trained on). Locking turns "the same gold set" from an
assumption into a check: once data/gold/LOCK.json exists, CI and eval verify
the hashes, so an edit to a gold file fails loudly until someone re-locks on
purpose - and a re-lock shows up in review as a change to LOCK.json.

    python Src/source/data_prep/gold_lock.py status   # what is left before it can be locked
    python Src/source/data_prep/gold_lock.py lock     # write data/gold/LOCK.json
    python Src/source/data_prep/gold_lock.py verify   # 0 = matches, 1 = changed, 2 = not locked

What gets locked, per dataset: the gold messages (data/gold/<ds>_gold.jsonl)
and their checked rewrites (data/gold_drafts/<ds>_gold_draft.jsonl). `lock`
refuses until every dataset has 60 of each, the same ids and source text in
both, a rewrite and 1-3 notes in every draft, and a checked_by on every draft.

Run from anywhere; paths are anchored to the repo root. Standard library
only. Prints counts and ids, never message text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DATASETS = ("enron", "stanford", "circa")
PER_DATASET = 60
LOCK_FILE = Path("data/gold/LOCK.json")


def gold_files(dataset: str) -> tuple[Path, Path]:
    """(gold messages, checked rewrites), relative to the repo root."""
    return Path(f"data/gold/{dataset}_gold.jsonl"), Path(f"data/gold_drafts/{dataset}_gold_draft.jsonl")


def _rows(path: Path) -> list[dict[str, Any]]:
    """Strict: a line that isn't a JSON object is an error, not something to skip."""
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"line {n} is not a JSON object")
        rows.append(row)
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def problems(root: Path = ROOT) -> dict[str, list[str]]:
    """Per dataset, what stops the gold set being locked. All empty = ready."""
    out: dict[str, list[str]] = {}
    for ds in DATASETS:
        issues: list[str] = []
        loaded = {}
        for kind, rel in zip(("gold", "drafts"), gold_files(ds)):
            if not (root / rel).is_file():
                issues.append(f"no {rel}")
                continue
            try:
                loaded[kind] = _rows(root / rel)
            except ValueError as exc:      # JSONDecodeError is a ValueError
                issues.append(f"{rel} is unreadable: {exc}")
                continue
            rows = loaded[kind]
            ids = [r.get("id") for r in rows]
            if len(rows) != PER_DATASET:
                issues.append(f"{len(rows)} {kind}, need {PER_DATASET}")
            if len(set(ids)) != len(ids) or None in ids:
                issues.append(f"{kind} ids are missing or repeated")

        drafts = loaded.get("drafts", [])
        unchecked = sum(not str(d.get("checked_by") or "").strip() for d in drafts)
        if unchecked:
            issues.append(f"{unchecked} drafts not checked (no checked_by)")
        incomplete = sum(not str(d.get("rewrite") or "").strip()
                         or not isinstance(d.get("notes"), list) or not 1 <= len(d["notes"]) <= 3
                         for d in drafts)
        if incomplete:
            issues.append(f"{incomplete} drafts without a rewrite and 1-3 notes")

        if "gold" in loaded and "drafts" in loaded:
            gold = {r.get("id"): r.get("source") for r in loaded["gold"]}
            draft = {r.get("id"): r.get("source") for r in loaded["drafts"]}
            if gold.keys() != draft.keys():
                issues.append(f"draft ids differ from gold ids ({len(gold.keys() - draft.keys())} "
                              f"gold without a draft, {len(draft.keys() - gold.keys())} drafts not in gold)")
            else:
                changed = sum(gold[i] != draft[i] for i in gold)
                if changed:
                    issues.append(f"{changed} drafts have different source text from gold")
        out[ds] = issues
    return out


def lock(root: Path = ROOT) -> dict[str, Any]:
    """Write LOCK.json, or raise SystemExit listing what isn't ready."""
    blocking = {ds: issues for ds, issues in problems(root).items() if issues}
    if blocking:
        lines = [f"  {ds}: {issue}" for ds, issues in blocking.items() for issue in issues]
        raise SystemExit("gold is not ready to lock:\n" + "\n".join(lines))
    record = {
        "locked_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "per_dataset": PER_DATASET,
        "files": {str(rel): _sha256(root / rel) for ds in DATASETS for rel in gold_files(ds)},
    }
    (root / LOCK_FILE).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def changed_since_lock(root: Path = ROOT) -> list[str] | None:
    """Locked files whose hash no longer matches, or None if gold isn't locked."""
    if not (root / LOCK_FILE).is_file():
        return None
    locked = json.loads((root / LOCK_FILE).read_text(encoding="utf-8"))["files"]
    return [rel for rel, sha in locked.items()
            if not (root / rel).is_file() or _sha256(root / rel) != sha]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("command", choices=("status", "lock", "verify"))
    args = ap.parse_args(argv)

    if args.command == "status":
        changed = changed_since_lock(ROOT)
        if changed is None:
            print("lock: none yet")
        else:
            print("lock: " + ("matches" if not changed else "CHANGED since locking: " + ", ".join(changed)))
        for ds, issues in problems(ROOT).items():
            print(f"{ds:9} " + ("ready" if not issues else "; ".join(issues)))
        return 0

    if args.command == "lock":
        record = lock(ROOT)
        print(f"locked {len(record['files'])} files -> {LOCK_FILE}")
        return 0

    changed = changed_since_lock(ROOT)
    if changed is None:
        print(f"gold is not locked yet ({LOCK_FILE} does not exist)")
        return 2
    if changed:
        print("gold changed since it was locked: " + ", ".join(changed))
        return 1
    print(f"gold matches {LOCK_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
