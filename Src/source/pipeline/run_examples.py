"""Run the pipeline over examples/messages.json and write the results out.

The point of this script is comparison. Two independent prompt axes:

    --no-model-comments     drop the three model comments
    --no-extracted-spans    drop the extractor's spans ("LLM leads")

    --sweep     run all four combinations and print them side by side
    --both      just the model-comments axis (two runs)
    --dry-run   no LLM call; analysis, prompt and templated fallback only

Everything except the toggled block is identical between runs, so any
difference is attributable to the thing being toggled.

Calls run concurrently, because they are independent and the endpoint is the
bottleneck. Measured against NVIDIA-hosted kimi-k3 at roughly five minutes
per call, eighty serial calls is about six and a half hours; eight at a time
is under an hour. Raise --workers until the endpoint starts refusing, then
back off.

Nothing written here contains a message body beyond what the examples file
already holds on disk, and no message text is logged.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parents[2]) not in sys.path:  # repo root, so `Src.` imports resolve
    sys.path.insert(0, str(HERE.parents[2]))

from Src.source.pipeline.analysis import analyse  # noqa: E402
from Src.source.pipeline.config import load  # noqa: E402
from Src.source.pipeline.pipeline import run  # noqa: E402
from Src.source.pipeline.prompt import build  # noqa: E402
from Src.source.pipeline.validator import templated_output  # noqa: E402

EXAMPLES = HERE / "examples" / "messages.json"
DEFAULT_OUT = HERE / "examples"


def run_one(example: dict, config, dry_run: bool) -> dict:
    """One example. Never raises - a single bad example must not end the run."""
    started = time.time()
    try:
        message = example["message"]
        analysis = analyse(message)
        record = {
            "id": example["id"],
            "expected_type": example.get("expected_type"),
            "detected_type": analysis.message_type,
            "type_matches": analysis.message_type == example.get("expected_type"),
            "found": sorted(analysis.extraction.found),
            "actions": len(analysis.extraction.actions),
            "missing": analysis.extraction.missing,
            "comments": analysis.comments,
            "prompt_chars": len(build(analysis, "review", config)),
        }
        record["result"] = (
            templated_output(analysis, ["dry run - no LLM call"]) if dry_run
            else run(message, "review", config)
        )
    except Exception as exc:  # noqa: BLE001 - one example must not sink the run
        record = {
            "id": example.get("id"),
            "error": type(exc).__name__,
            "result": {"degraded": True,
                       "degraded_reason": [type(exc).__name__]},
        }
    record["seconds"] = round(time.time() - started, 1)
    return record


def summarise(records: list[dict]) -> dict:
    total = len(records) or 1
    degraded = sum(1 for r in records if r["result"].get("degraded"))
    checked = [
        r for r in records
        if isinstance(r["result"].get("cross_check"), dict)
        and r["result"]["cross_check"].get("agreement_rate") is not None
    ]
    return {
        "examples": len(records),
        "errors": sum(1 for r in records if "error" in r),
        "message_type_correct": sum(1 for r in records if r.get("type_matches")),
        "degraded": degraded,
        "clean": len(records) - degraded,
        "mean_prompt_chars": round(
            sum(r.get("prompt_chars", 0) for r in records) / total),
        "mean_seconds": round(
            sum(r.get("seconds", 0) for r in records) / total, 1),
        "mean_cross_check_agreement": (
            round(sum(r["result"]["cross_check"]["agreement_rate"]
                      for r in checked) / len(checked), 3)
            if checked else None),
    }


def execute(config, dry_run: bool, label: str, out_dir: Path,
            workers: int, limit: int | None) -> dict:
    examples = json.loads(EXAMPLES.read_text(encoding="utf-8"))
    if limit:
        examples = examples[:limit]

    started = time.time()
    print(f"[{label}] {len(examples)} examples, {workers} workers...", flush=True)

    # Report each example as it lands rather than after the whole batch. A
    # reasoning model takes minutes per call, and a run that prints nothing
    # for twenty minutes is indistinguishable from a hung one.
    order = {e["id"]: i for i, e in enumerate(examples)}
    records: list[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(run_one, e, config, dry_run): e for e in examples}
        for done in as_completed(futures):
            record = done.result()
            records.append(record)
            result = record.get("result", {})
            state = ("ERROR " + record["error"]) if record.get("error") else (
                "degraded" if result.get("degraded") else "clean")
            reason = (result.get("degraded_reason") or [""])[0][:52]
            print(f"  [{len(records)}/{len(examples)}] {record.get('id'):<9} "
                  f"{record.get('seconds'):>6}s  {state}"
                  f"{'  ' + reason if reason else ''}", flush=True)
    records.sort(key=lambda r: order.get(r.get("id"), 0))

    summary = summarise(records)
    summary["wall_clock_seconds"] = round(time.time() - started, 1)

    out = out_dir / f"results_{label}.json"
    out.write_text(json.dumps({
        "summary": summary,
        "config": {
            "provider": config.llm.provider,
            "model": config.llm.model,
            "include_model_comments": config.include_model_comments,
            "include_extracted_spans": config.include_extracted_spans,
            "dry_run": dry_run,
        },
        "records": records,
    }, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"[{label}] {summary}\n         -> {out}", flush=True)
    return summary


# The two axes, as four named combinations.
VARIANTS: dict[str, tuple[bool, bool]] = {
    "spans+comments": (True, True),
    "spans_only": (True, False),
    "comments_only": (False, True),
    "neither": (False, False),
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-model-comments", action="store_true",
                        help="drop the three model comments from the prompt")
    parser.add_argument("--no-extracted-spans", action="store_true",
                        help="drop the extractor's spans - 'LLM leads'")
    parser.add_argument("--both", action="store_true",
                        help="the model-comments axis only (2 runs)")
    parser.add_argument("--sweep", action="store_true",
                        help="all four combinations of the two axes")
    parser.add_argument("--dry-run", action="store_true",
                        help="skip the LLM call entirely")
    parser.add_argument("--workers", type=int, default=4,
                        help="concurrent calls (default 4)")
    parser.add_argument("--limit", type=int,
                        help="only the first N examples - use for a pilot run")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    base = load()
    common = dict(out_dir=args.out, workers=args.workers, limit=args.limit)

    if args.sweep:
        results = {}
        for label, (spans, comments) in VARIANTS.items():
            results[label] = execute(
                replace(base, include_extracted_spans=spans,
                        include_model_comments=comments),
                args.dry_run, label, **common)
        rows = ["degraded", "clean", "message_type_correct",
                "mean_cross_check_agreement", "mean_prompt_chars",
                "mean_seconds", "wall_clock_seconds"]
        print(f"\n{'metric':<30}" + "".join(f"{v:>17}" for v in VARIANTS))
        print("-" * (30 + 17 * len(VARIANTS)))
        for key in rows:
            print(f"{key:<30}" + "".join(
                f"{str(results[v].get(key)):>17}" for v in VARIANTS))
        return

    if args.both:
        for label, comments in (("with_comments", True), ("without_comments", False)):
            execute(replace(base, include_model_comments=comments),
                    args.dry_run, label, **common)
        return

    config = replace(
        base,
        include_model_comments=not args.no_model_comments,
        include_extracted_spans=not args.no_extracted_spans,
    )
    label = ("spans" if config.include_extracted_spans else "nospans") + \
            ("_comments" if config.include_model_comments else "_nocomments")
    execute(config, args.dry_run, label, **common)


if __name__ == "__main__":
    main()
