"""Ship check: does the fine-tuned Compose model ship, or the few-shot baseline?

CLAUDE.md's rule, on the "all" rows of eval/results.csv (every gold dataset
pooled):

    1. the fine-tuned model beats the baseline with the pairwise judge: more
       wins than losses over the pairs both orders agreed on
    2. its entity recall is no more than 2 points below the baseline's
    3. its NLI entailment is no more than 2 points below the baseline's

The verdict only counts once the judge has been validated against the human
rubric scores (eval/judge_validation.json from validate_judge: Spearman >= 0.6
on the total) and the gold set is locked and unchanged (data/gold/LOCK.json).
Until then the answer is UNDECIDED, and --preview shows what it would be.
Either way both models' numbers are in results.csv, to report.

usage (repo root):
    python -m Src.source.pipeline.ship_check --finetuned run2 [--preview]

exit status: 0 the fine-tuned model ships, 1 the baseline ships, 2 undecided.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from Src.source.pipeline.eval_report import gold_lock_status

MAX_DROP = 0.02          # "no more than 2 points lower"


def _num(cell: str | None) -> float | None:
    return float(cell) if cell not in (None, "") else None


def decide(base: dict[str, str], ft: dict[str, str], *, judge_trusted: bool | None,
           gold_lock: str, preview: bool) -> dict[str, Any]:
    wins, losses = _num(ft.get("judge_wins")), _num(ft.get("judge_losses"))
    judged = wins is not None and losses is not None
    rules = [{"rule": "judge win rate", "ok": judged and wins > losses,
              "detail": (f"won {wins:.0f}, lost {losses:.0f}, {ft.get('judge_ties') or 0} ties, "
                         f"{ft.get('judge_no_decision') or 0} without a decision"
                         if judged else "no judge results in results.csv")}]
    for metric in ("entity_recall", "nli_entailment"):
        b, f = _num(base.get(metric)), _num(ft.get(metric))
        ok = b is not None and f is not None and round(f - b, 6) >= -MAX_DROP
        rules.append({"rule": metric, "ok": ok,
                      "detail": f"{f:.3f} vs baseline {b:.3f}" if b is not None and f is not None
                      else "missing from results.csv"})
    preconditions = [
        {"rule": "judge validated against human scores", "ok": bool(judge_trusted),
         "detail": {None: "no eval/judge_validation.json yet", True: "Spearman >= 0.6",
                    False: "Spearman below 0.6"}[judge_trusted]},
        {"rule": "gold locked and unchanged", "ok": gold_lock == "locked", "detail": gold_lock},
    ]
    if all(r["ok"] for r in preconditions) or preview:
        verdict = f"SHIP {ft['model']}" if all(r["ok"] for r in rules) else f"SHIP {base['model']}"
    else:
        verdict = "UNDECIDED"
    if preview and not all(r["ok"] for r in preconditions):
        verdict = f"PREVIEW: {verdict}"
    return {"verdict": verdict, "baseline": base["model"], "finetuned": ft["model"],
            "rules": rules, "preconditions": preconditions}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--finetuned", required=True)
    ap.add_argument("--baseline", default="baseline")
    ap.add_argument("--eval-dir", type=Path, default=Path("eval"))
    ap.add_argument("--preview", action="store_true",
                    help="give the verdict even before the judge is validated and the gold locked")
    args = ap.parse_args(argv)

    with (args.eval_dir / "results.csv").open(encoding="utf-8", newline="") as f:
        rows = {r["model"]: r for r in csv.DictReader(f) if r["dataset"] == "all"}
    for name in (args.baseline, args.finetuned):
        if name not in rows:
            raise SystemExit(f"no 'all' row for {name} in {args.eval_dir / 'results.csv'} - run eval_report first")
    validation = args.eval_dir / "judge_validation.json"
    trusted = json.loads(validation.read_text(encoding="utf-8")).get("trust_judge") if validation.is_file() else None

    result = decide(rows[args.baseline], rows[args.finetuned], judge_trusted=trusted,
                    gold_lock=gold_lock_status(), preview=args.preview)
    for r in result["preconditions"] + result["rules"]:
        print(f"  [{'ok' if r['ok'] else '--'}] {r['rule']}: {r['detail']}")
    print(result["verdict"])
    (args.eval_dir / "ship_decision.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if result["verdict"].startswith("SHIP"):
        return 0 if result["verdict"] == f"SHIP {args.finetuned}" else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
