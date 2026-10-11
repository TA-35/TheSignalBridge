"""Eval report for the Compose models: eval/results.csv and eval/worst20_<model>.md.

Reads, under eval/ (paths from the repo root):
    <dataset>/<model>.jsonl          predictions, from
                                     compose_client --input data/gold/<dataset>_gold.jsonl
                                     --temperature 0 --out eval/<dataset>/<model>.jsonl
                                     (with --few-shot for the baseline only)
    <dataset>/<baseline>_vs_<model>/ run_judge output, --a <baseline> --b <model>  (optional)
    <dataset>/<model>_scores.jsonl   the rubric scores from `score` below            (optional)

Writes:
    results.csv          one row per model per dataset, plus "all" pooling the datasets
    results_meta.json    what the numbers came from: file hashes, prompt, judge, gold lock
    worst20_<model>.md   each model's 20 worst outputs, worst first

BERTScore needs a human-checked gold rewrite, so it is only filled in for a
dataset whose data/gold_drafts/<dataset>_gold_draft.jsonl has checked_by on
every row. The metrics themselves are in eval_metrics.py.

usage (repo root):
    python -m Src.source.pipeline.eval_report score  --models baseline run2
    python -m Src.source.pipeline.eval_report report --baseline baseline --models run2
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from Src.source.data_prep import filter_pairs as fp
from Src.source.pipeline import bertscore as bs
from Src.source.pipeline import compose_prompt as cp
from Src.source.pipeline import eval_metrics as em
from Src.source.pipeline import judge as J

DATASETS = ("enron", "stanford", "circa")
CRITERIA = ("meaning_kept", "clarity", "warmth", "notes_accurate")
COLUMNS = ["dataset", "model", "n", "json_valid", "entity_recall", "nli_entailment", "grounded",
           "added_entity_rate", "nli_contradiction", "circa_direct_rate", "circa_answer_stated_rate",
           "politeness_drop_rate",
           "politeness_to_low_rate", "length_ratio", "bertscore_f1", "notes_accurate", "rubric_total",
           "judge_vs", "judge_wins", "judge_losses", "judge_ties", "judge_no_decision", "judge_win_rate"]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gold_lock_status(root: Path = Path(".")) -> str:
    """"locked", "not locked" or "CHANGED since lock: ...", from data/gold/LOCK.json
    (written by data_prep/gold_lock.py)."""
    lock = root / "data" / "gold" / "LOCK.json"
    if not lock.is_file():
        return "not locked"
    files = json.loads(lock.read_text(encoding="utf-8"))["files"]
    changed = [rel for rel, digest in files.items()
               if not (root / rel).is_file() or sha256(root / rel) != digest]
    return f"CHANGED since lock: {', '.join(changed)}" if changed else "locked"


def load_predictions(path: Path, *, few_shot: bool) -> dict[str, dict[str, Any]]:
    """Predictions by id. Refuses a file made with another prompt, or a baseline
    run zero-shot / a fine-tuned model run few-shot: either makes the comparison
    meaningless without looking wrong."""
    preds = {}
    for r in read_jsonl(path):
        prompt = r.get("prompt") or r.get("prompt_version")
        if prompt != cp.fingerprint():
            raise SystemExit(f"{path}: {r.get('id')} was made with prompt {prompt}, "
                             f"this checkout's is {cp.fingerprint()} - regenerate it")
        if bool(r.get("few_shot")) != few_shot:
            raise SystemExit(f"{path}: {r.get('id')} has few_shot={r.get('few_shot')}; the baseline "
                             "runs with --few-shot and the fine-tuned models without")
        preds[r["id"]] = r
    return preds


def checked_gold(drafts: Path) -> dict[str, str] | None:
    """The human-checked gold rewrites by id, or None unless every draft is checked."""
    if not drafts.is_file():
        return None
    rows = read_jsonl(drafts)
    if not rows or not all(str(r.get("checked_by") or "").strip() for r in rows):
        return None
    return {r["id"]: r["rewrite"] for r in rows}


def judge_pairs(eval_dir: Path, dataset: str, baseline: str, model: str):
    """(summary, {id: verdict row}) of run_judge baseline vs model, or (None, {})."""
    out = eval_dir / dataset / f"{baseline}_vs_{model}"
    if not (out / "judge_summary.json").is_file():
        return None, {}
    summary = json.loads((out / "judge_summary.json").read_text(encoding="utf-8"))
    if summary.get("rubric") != J.RUBRIC_ID:
        raise SystemExit(f"{out} was judged with rubric {summary.get('rubric')}, this judge is {J.RUBRIC_ID} - "
                         "move it aside and run run_judge again")
    return summary, {r["id"]: r for r in read_jsonl(out / "judge_pairs.jsonl")}


def rubric(eval_dir: Path, dataset: str, model: str) -> dict[str, dict[str, Any]]:
    path = eval_dir / dataset / f"{model}_scores.jsonl"
    """Rubric scores by id, made with the current judge rubric (older ones are
    ignored, and `score` redoes them)."""
    rows = read_jsonl(path) if path.is_file() else []
    return {r["id"]: r for r in rows if "error" not in r and r.get("rubric") == J.RUBRIC_ID}


# ---------------------------------------------------------------- score
def score(models: list[str], datasets: tuple[str, ...], eval_dir: Path, gold_dir: Path,
          baseline: str, workers: int = 5) -> None:
    """The judge's 0-2 rubric scores (judge.score_output) for every usable
    prediction, for change-note accuracy. Resumable: scored ids are skipped and
    failed ones (a rate limit, an unparseable reply) are tried again."""
    for dataset in datasets:
        gold = {g["id"]: g for g in read_jsonl(gold_dir / f"{dataset}_gold.jsonl")}
        for model in models:
            preds = load_predictions(eval_dir / dataset / f"{model}.jsonl", few_shot=model == baseline)
            cache = eval_dir / dataset / f"{model}_scores.jsonl"
            done = set(rubric(eval_dir, dataset, model))
            todo = [i for i, p in preds.items() if em.usable(p) and i not in done and i in gold]

            def one(rid):
                p = preds[rid]
                try:
                    s = J.score_output(gold[rid]["source"], None, p)
                    return {"id": rid, **{c: getattr(s, c) for c in CRITERIA}, "total": s.total,
                            "judge": s.model, "rubric": J.RUBRIC_ID}
                except J.JudgeError as exc:
                    return {"id": rid, "error": str(exc)}

            with cache.open("a", encoding="utf-8") as f, ThreadPoolExecutor(max_workers=workers) as pool:
                failed = 0
                for row in pool.map(one, todo):
                    failed += "error" in row
                    f.write(json.dumps(row) + "\n")
                    f.flush()
            print(f"{dataset}/{model}: scored {len(todo) - failed}, failed {failed}, "
                  f"{len(done)} already done", flush=True)


# ---------------------------------------------------------------- report
def _mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def _judge_cells(summaries: list[dict[str, Any]], baseline: str, model: str) -> dict[str, Any]:
    if not summaries:
        return {}
    wins = sum(s.get(f"wins_{model}", 0) for s in summaries)
    losses = sum(s.get(f"wins_{baseline}", 0) for s in summaries)
    return {"judge_vs": baseline, "judge_wins": wins, "judge_losses": losses,
            "judge_ties": sum(s.get("ties", 0) for s in summaries),
            "judge_no_decision": sum(s.get("no_decision", 0) for s in summaries),
            "judge_win_rate": wins / (wins + losses) if wins + losses else None}


def build(baseline: str, models: list[str], datasets: tuple[str, ...], eval_dir: Path,
          gold_dir: Path, drafts_dir: Path, *, metrics=em.score_predictions, f1_fn=None):
    """results.csv rows, per-message rows and predictions per model (for worst-20),
    and the meta record. `metrics` and `f1_fn` are injectable for the tests."""
    everyone = [baseline] + [m for m in models if m != baseline]
    rows_out, per_message, all_preds = [], {m: [] for m in everyone}, {m: {} for m in everyone}
    meta: dict[str, Any] = {"created": time.strftime("%Y-%m-%d %H:%M:%S"), "prompt_fingerprint": cp.fingerprint(),
                            "prompt_version": cp.PROMPT_VERSION, "judge_model": J.JUDGE_MODEL,
                            "judge_rubric": J.RUBRIC_ID, "baseline": baseline, "models": everyone,
                            "gold": {}, "predictions": {}, "bertscore": {}, "gold_lock": gold_lock_status()}
    pooled = {m: {"rows": [], "f1": [], "rubric": [], "judge": []} for m in everyone}
    for dataset in datasets:
        gold_path = gold_dir / f"{dataset}_gold.jsonl"
        gold = read_jsonl(gold_path)
        meta["gold"][str(gold_path)] = sha256(gold_path)
        preds = {}
        for m in everyone:
            path = eval_dir / dataset / f"{m}.jsonl"
            if not path.is_file():
                raise SystemExit(f"missing {path} - generate it with compose_client (see the docstring)")
            preds[m] = load_predictions(path, few_shot=m == baseline)
            all_preds[m].update(preds[m])
            meta["predictions"][str(path)] = sha256(path)

        refs = checked_gold(drafts_dir / f"{dataset}_gold_draft.jsonl")
        f1 = {m: {} for m in everyone}
        if refs is None:
            meta["bertscore"][dataset] = "skipped: gold rewrites not all human-checked"
        else:
            ids = [g["id"] for g in gold if g["id"] in refs and all(em.usable(preds[m].get(g["id"], {"error": 1}))
                                                                   for m in everyone)]
            score_fn = f1_fn or bs.f1_scores
            for m in everyone:
                f1[m] = dict(zip(ids, score_fn([preds[m][i]["rewrite"] for i in ids], [refs[i] for i in ids])))
            meta["bertscore"][dataset] = f"{len(ids)} ids every model answered"

        for m in everyone:
            rows = metrics(gold, preds[m])
            scores = rubric(eval_dir, dataset, m)
            summary, verdicts = judge_pairs(eval_dir, dataset, baseline, m) if m != baseline else (None, {})
            for r in rows:
                r["model"] = m
                r["f1"] = f1[m].get(r["id"])
                r["rubric"] = scores.get(r["id"])
                r["verdict"] = verdicts.get(r["id"])
            per_message[m] += rows
            pooled[m]["rows"] += rows
            pooled[m]["f1"] += list(f1[m].values())
            pooled[m]["rubric"] += list(scores.values())
            if summary:
                pooled[m]["judge"].append(summary)
            rows_out.append({"dataset": dataset, "model": m, **em.summarize(rows),
                             "bertscore_f1": _mean(f1[m].values()),
                             "notes_accurate": _mean(s["notes_accurate"] for s in scores.values()),
                             "rubric_total": _mean(s["total"] for s in scores.values()),
                             **_judge_cells([summary] if summary else [], baseline, m)})

    for m in everyone:
        p = pooled[m]
        rows_out.append({"dataset": "all", "model": m, **em.summarize(p["rows"]),
                         "bertscore_f1": _mean(p["f1"]),
                         "notes_accurate": _mean(s["notes_accurate"] for s in p["rubric"]),
                         "rubric_total": _mean(s["total"] for s in p["rubric"]),
                         **_judge_cells(p["judge"], baseline, m)})
    return rows_out, per_message, all_preds, meta


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: round(v, 4) if isinstance(v, float) else v for k, v in r.items()})


# ---------------------------------------------------------------- worst 20
def problems(row: dict[str, Any], gold: dict[str, Any], pred: dict[str, Any]) -> tuple[int, list[str]]:
    """How bad one output is (higher is worse) and why, in words."""
    if not row["usable"]:
        return 100, [f"no usable answer ({row.get('error')})"]
    points, why = 0, []
    if not row["grounded"]:
        points += 10
        record = {"source": gold["source"], "rewrite": pred["rewrite"]}
        why += [x for x in (fp.check_dropped(record), fp.check_added(record)) if x]
        if row.get("nli") == "contradiction":
            why.append("NLI reads it as contradicting the message")
    verdict = row.get("verdict")
    if verdict and verdict["winner"] not in (row["model"], "tie", "no_decision"):
        points += 5
        why.append(f"judge preferred {verdict['winner']} in both orders")
    if row.get("rubric"):
        points += 8 - row["rubric"]["total"]
        if row["rubric"]["total"] <= 6:
            why.append("rubric " + ", ".join(f"{c} {row['rubric'][c]}" for c in CRITERIA)
                       + f" ({row['rubric']['total']}/8)")
    if row.get("is_circa") and row.get("circa_direct") is False:
        why.append("Circa classifier still reads the reply as indirect")
    if row.get("politeness") and em.POLITENESS_ORDER[row["politeness"][1]] < em.POLITENESS_ORDER[row["politeness"][0]]:
        why.append(f"politeness fell {row['politeness'][0]} -> {row['politeness'][1]}")
    return points, why


def worst20(model: str, rows: list[dict[str, Any]], gold: dict[str, dict], preds: dict[str, dict]) -> str:
    ranked = []
    for r in rows:
        points, why = problems(r, gold[r["id"]], preds.get(r["id"], {}))
        if points or why:
            ranked.append((-points, r["f1"] if r["f1"] is not None else 1.0, r["id"], r, why))
    ranked.sort(key=lambda t: t[:3])
    md = [f"# Worst 20: {model}\n",
          "Ranked by: no usable answer, then failing the grounding check, then losing to the "
          "baseline in both judge orders, then the rubric score; ties go to the lower BERTScore.\n"]
    for n, (_, _, rid, r, why) in enumerate(ranked[:20], 1):
        g, p = gold[rid], preds.get(rid, {})
        question, message = fp.split_circa(g["source"])
        md.append(f"## {n}. {rid} ({r['dataset']})\n")
        md.append("- " + "\n- ".join(why or ["minor issues only"]) + "\n")
        if question is not None:
            md.append(f"**Question:** {question}\n")
        md.append(f"**Message:** {message}\n")
        if r["usable"]:
            md.append(f"**Rewrite:** {p['rewrite']}\n")
            md.append("*Notes:* " + " / ".join(p.get("notes") or []) + "\n")
        verdict = r.get("verdict")
        if verdict:
            md.append(f"Judge, A first: {verdict['order_ab']['reason']}  \n"
                      f"Judge, B first: {verdict['order_ba']['reason']}\n")
        if r["f1"] is not None:
            md.append(f"BERTScore vs gold: {r['f1']:.3f}\n")
    if not ranked:
        md.append("No problems found.\n")
    return "\n".join(md)


def report(baseline: str, models: list[str], datasets: tuple[str, ...], eval_dir: Path,
           gold_dir: Path, drafts_dir: Path) -> None:
    rows, per_message, all_preds, meta = build(baseline, models, datasets, eval_dir, gold_dir, drafts_dir)
    write_csv(rows, eval_dir / "results.csv")
    (eval_dir / "results_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    gold = {g["id"]: g for ds in datasets for g in read_jsonl(gold_dir / f"{ds}_gold.jsonl")}
    for m, rows_m in per_message.items():
        (eval_dir / f"worst20_{m}.md").write_text(worst20(m, rows_m, gold, all_preds[m]), encoding="utf-8")
    show = ["model", "json_valid", "entity_recall", "nli_entailment", "grounded", "circa_direct_rate",
            "bertscore_f1", "notes_accurate", "judge_win_rate"]
    print(" | ".join(show))
    for r in rows:
        if r["dataset"] == "all":
            print(" | ".join(f"{r.get(k):.3f}" if isinstance(r.get(k), float) else str(r.get(k)) for k in show))
    print(f"wrote {eval_dir / 'results.csv'}, results_meta.json and worst20_<model>.md "
          f"(gold: {meta['gold_lock']})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("score", "report"):
        p = sub.add_parser(name)
        p.add_argument("--baseline", default="baseline")
        p.add_argument("--models", nargs="+", required=True)
        p.add_argument("--datasets", nargs="+", default=list(DATASETS), choices=DATASETS)
        p.add_argument("--eval-dir", type=Path, default=Path("eval"))
        p.add_argument("--gold-dir", type=Path, default=Path("data/gold"))
        p.add_argument("--drafts-dir", type=Path, default=Path("data/gold_drafts"))
    args = ap.parse_args(argv)
    if args.cmd == "score":
        score(args.models, tuple(args.datasets), args.eval_dir, args.gold_dir, args.baseline)
    else:
        report(args.baseline, args.models, tuple(args.datasets), args.eval_dir, args.gold_dir, args.drafts_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
