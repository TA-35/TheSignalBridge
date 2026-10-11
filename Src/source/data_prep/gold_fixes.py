"""Apply a reviewed set of gold-draft fixes and mark the drafts as checked.

The gold set is human-verified (CLAUDE.md): a person reads all 60 drafts of a
dataset against the spot-check list in docs/COMPOSE_STYLE_GUIDE.md. To make
that quicker, data/gold_drafts/<dataset>_gold_fixes.json holds proposed fixes,
keyed by draft id, each with the reason and the fields to replace:

    {"stanford_00049": {"why": "...", "status": "proposed",
                        "rewrite": "...", "notes": ["..."], "meaning": {"implied": "..."}}}

The checker sets every status to "accept" or "reject" (editing the proposed
text first if they want), fixes anything else by hand in the drafts file, and
then runs, from the repo root:

    python Src/source/data_prep/gold_fixes.py <dataset> --checked-by <name>

That applies the accepted fixes, sets checked_by on every draft, and refuses
while any fix is still "proposed" or a fixed draft would fail the filter's
format checks.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):                      # run as a script from the repo root
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from Src.source.data_prep import filter_pairs as fp  # noqa: E402

MEANING_KEYS = {"ask", "deadline", "urgency", "tone", "implied"}
URGENCY = {"low", "medium", "high"}


def apply(drafts: list[dict], fixes: dict[str, dict], checked_by: str) -> tuple[list[dict], dict[str, int]]:
    """The drafts with the accepted fixes applied and checked_by on every row.
    Raises ValueError listing every problem, so nothing is half-applied."""
    if not checked_by.strip():
        raise ValueError("checked_by is empty - say who checked the drafts")
    ids = {d["id"] for d in drafts}
    problems = []
    for rid, fix in fixes.items():
        status = fix.get("status")
        if rid not in ids:
            problems.append(f"{rid}: no draft with this id")
        if status not in ("accept", "reject"):
            problems.append(f"{rid}: status is {status!r} - set it to \"accept\" or \"reject\"")
        bad_keys = set(fix.get("meaning") or {}) - MEANING_KEYS
        if bad_keys:
            problems.append(f"{rid}: unknown meaning fields {sorted(bad_keys)}")
    out, counts = [], {"accepted": 0, "rejected": 0}
    for d in drafts:
        row = dict(d)
        fix = fixes.get(d["id"])
        if fix and fix.get("status") == "accept":
            counts["accepted"] += 1
            for key in ("rewrite", "notes"):
                if key in fix:
                    row[key] = fix[key]
            if fix.get("meaning"):
                row["meaning"] = {**row.get("meaning", {}), **fix["meaning"]}
            for check in (fp.check_json, fp.check_notes):
                msg = check(row)
                if msg:
                    problems.append(f"{d['id']}: after the fix, {msg}")
            if row["meaning"].get("urgency") not in URGENCY:
                problems.append(f"{d['id']}: urgency {row['meaning'].get('urgency')!r} is not low/medium/high")
        elif fix:
            counts["rejected"] += 1
        row.pop("checked_by", None)
        row["checked_by"] = checked_by.strip()
        out.append(row)
    if problems:
        raise ValueError("\n".join(problems))
    return out, counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dataset", choices=("enron", "stanford", "circa"))
    ap.add_argument("--checked-by", required=True)
    ap.add_argument("--dir", type=Path, default=Path("data/gold_drafts"))
    args = ap.parse_args(argv)

    drafts_path = args.dir / f"{args.dataset}_gold_draft.jsonl"
    fixes_path = args.dir / f"{args.dataset}_gold_fixes.json"
    drafts = [json.loads(line) for line in drafts_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    fixes = json.loads(fixes_path.read_text(encoding="utf-8")) if fixes_path.is_file() else {}
    try:
        rows, counts = apply(drafts, fixes, args.checked_by)
    except ValueError as exc:
        print(f"not applied - fix these first:\n{exc}")
        return 1
    drafts_path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    print(f"{drafts_path}: {counts['accepted']} fixes applied, {counts['rejected']} rejected, "
          f"checked_by={args.checked_by!r} on all {len(rows)} drafts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
