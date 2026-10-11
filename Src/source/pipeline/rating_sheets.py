"""Blind rating sheets, to validate the LLM judge against people (EVAL_harness.md).

make     picks N gold messages per dataset (seeded), takes the baseline's and the
         fine-tuned model's output for each, and writes one sheet per rater with
         the rows in that rater's own random order and the model hidden:
             eval/rating/sheet_<rater>.csv   item, question, message, rewrite, notes,
                                             meaning; then the four scores and a
                                             comment, left blank to fill in
             eval/rating/key.json            item -> id, dataset, model
             eval/rating/README.md           the rubric, in the judge's own words
collect  reads the filled sheets back into eval/human_scores.csv, the file
         validate_judge reads (model = baseline | finetuned).

usage (repo root):
    python -m Src.source.pipeline.rating_sheets make --finetuned run2 --raters sanket yvonne
    python -m Src.source.pipeline.rating_sheets collect
"""
from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

from Src.source.data_prep import filter_pairs as fp
from Src.source.pipeline import eval_metrics as em
from Src.source.pipeline.eval_report import CRITERIA, DATASETS, load_predictions, read_jsonl

SHEET_COLUMNS = ["item", "question", "message", "rewrite", "notes", "meaning", *CRITERIA, "comment"]
HUMAN_COLUMNS = ["id", "dataset", "model", "rater", *CRITERIA, "comment"]


def _meaning(m: dict) -> str:
    return "; ".join(f"{k}: {m.get(k, '')}" for k in ("ask", "deadline", "urgency", "tone", "implied"))


def rubric_text() -> str:
    from Src.source.pipeline.judge import SCORE_SYSTEM

    criteria = SCORE_SYSTEM[SCORE_SYSTEM.index("Score each criterion"):SCORE_SYSTEM.index("Reply with")].strip()
    return ("# Rating the Compose rewrites\n\n"
            "Each row is one original message (with the question it answers, for Circa replies) "
            "and one rewrite of it, with the rewrite's notes and the meaning it extracted. Score "
            "the rewrite against the original only - there is no reference answer - and don't "
            "try to work out which model wrote it. Put 0, 1 or 2 in each of the four score "
            "columns; the comment is optional. Rate on your own, and don't open key.json until "
            "you've finished: it says which model wrote each row.\n\n" + criteria + "\n")


def make(baseline: str, finetuned: str, raters: list[str], per_dataset: int, seed: int,
         eval_dir: Path, gold_dir: Path) -> Path:
    rng = random.Random(seed)
    items = []
    for dataset in DATASETS:
        gold = {g["id"]: g for g in read_jsonl(gold_dir / f"{dataset}_gold.jsonl")}
        preds = {role: load_predictions(eval_dir / dataset / f"{name}.jsonl", few_shot=role == "baseline")
                 for role, name in (("baseline", baseline), ("finetuned", finetuned))}
        ids = sorted(i for i in gold if all(em.usable(preds[r].get(i, {"error": 1})) for r in preds))
        for rid in rng.sample(ids, min(per_dataset, len(ids))):
            question, message = fp.split_circa(gold[rid]["source"])
            for role in preds:
                p = preds[role][rid]
                items.append({"id": rid, "dataset": dataset, "model": role, "question": question or "",
                              "message": message, "rewrite": p["rewrite"], "notes": " / ".join(p["notes"]),
                              "meaning": _meaning(p["meaning"])})
    rng.shuffle(items)              # item numbers don't give the pairs or the models away
    for n, item in enumerate(items, 1):
        item["item"] = f"item_{n:02d}"

    out = eval_dir / "rating"
    out.mkdir(parents=True, exist_ok=True)
    key = {it["item"]: {"id": it["id"], "dataset": it["dataset"], "model": it["model"]} for it in items}
    (out / "key.json").write_text(json.dumps({"baseline": baseline, "finetuned": finetuned, "items": key},
                                             indent=2) + "\n", encoding="utf-8")
    (out / "README.md").write_text(rubric_text(), encoding="utf-8")
    for rater in raters:
        order = items[:]
        random.Random(f"{seed}-{rater}").shuffle(order)
        with (out / f"sheet_{rater}.csv").open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=SHEET_COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(order)
    print(f"{len(items)} items ({len(items) // 2} messages x 2 models) for {', '.join(raters)} -> {out}/")
    return out


def collect(eval_dir: Path) -> Path:
    rating = eval_dir / "rating"
    key = json.loads((rating / "key.json").read_text(encoding="utf-8"))["items"]
    rows, skipped = [], 0
    for sheet in sorted(rating.glob("sheet_*.csv")):
        rater = sheet.stem.removeprefix("sheet_")
        with sheet.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                scores = {c: str(r.get(c) or "").strip() for c in CRITERIA}
                if r.get("item") not in key or not all(v in ("0", "1", "2") for v in scores.values()):
                    skipped += 1
                    continue
                k = key[r["item"]]
                rows.append({"id": k["id"], "dataset": k["dataset"], "model": k["model"], "rater": rater,
                             **{c: int(v) for c, v in scores.items()}, "comment": r.get("comment", "")})
    out = eval_dir / "human_scores.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HUMAN_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} scored rows -> {out}; {skipped} rows not fully scored 0-2, left out")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    mk = sub.add_parser("make")
    mk.add_argument("--finetuned", required=True)
    mk.add_argument("--baseline", default="baseline")
    mk.add_argument("--raters", nargs="+", required=True)
    mk.add_argument("--per-dataset", type=int, default=5)
    mk.add_argument("--seed", type=int, default=42)
    mk.add_argument("--gold-dir", type=Path, default=Path("data/gold"))
    for p in (mk, sub.add_parser("collect")):
        p.add_argument("--eval-dir", type=Path, default=Path("eval"))
    args = ap.parse_args(argv)
    if args.cmd == "make":
        make(args.baseline, args.finetuned, args.raters, args.per_dataset, args.seed, args.eval_dir, args.gold_dir)
    else:
        collect(args.eval_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
