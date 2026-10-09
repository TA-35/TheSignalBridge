"""Generate training pairs with the teacher model (data step 2).

Sends every source message through the compose prompt (few-shot) to the
teacher on NVIDIA NIM and writes the answers where filter_pairs.py reads them:

    data/source/<dataset>_source.jsonl  ->  data/generated/<dataset>_gen.jsonl

With --gold it drafts rewrites for the gold set instead, for the team to check
by hand before the gold set is locked. Drafts have their own folder and never
go near data/generated/ (gold is never trained on):

    data/gold/<dataset>_gold.jsonl  ->  data/gold_drafts/<dataset>_gold_draft.jsonl

Teacher and settings are the ones in docs/COMPOSE_STYLE_GUIDE.md ("Teacher"):
deepseek-ai/deepseek-v4.1-flash, temperature 0.3, max_tokens 4000, messages
from compose_prompt.build_messages(few_shot=True).

Every record that gets an answer is written: a usable one with meaning,
rewrite and notes, an unusable one with the reply under `raw`, so the filter's
json_valid check rejects it and counts it. A record the API never answers
(timeouts and 5xx after retries) is not written, so running the same command
again picks up exactly those. Re-running is always safe: ids already in the
output file are skipped.

Run from the repo root. The key is NVIDIA_API_KEY, exported or in a .env
(the same files pipeline/config.py reads):

    python Src/source/data_prep/generate_pairs.py enron --limit 10       # try a few first
    python Src/source/data_prep/generate_pairs.py enron stanford          # the real run
    python Src/source/data_prep/generate_pairs.py enron stanford --gold   # gold drafts

Standard library only. Logs counts and ids, never message text.
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from Src.source.pipeline import compose_prompt as cp  # noqa: E402

URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "deepseek-ai/deepseek-v4.1-flash"
TEMPERATURE = 0.3
MAX_TOKENS = 4000           # it reasons before answering; the answer itself is under ~600
TIMEOUT = 300               # per request; the slowest bake-off answer took 51s
RETRY_CODES = {429, 500, 502, 503, 504}
BACKOFF = (10, 30, 60)      # seconds before each retry
DATASETS = ("enron", "stanford", "circa")
ENV_FILES = (ROOT / ".env", ROOT / "backend" / ".env", ROOT / "Src" / "source" / "pipeline" / ".env")


class TeacherError(RuntimeError):
    """No answer for this record, even after retries. Rerun to try it again."""


class TeacherConfigError(RuntimeError):
    """An error no retry will fix (bad key, unknown model). Stops the run."""


def api_key() -> str:
    """NVIDIA_API_KEY from the environment, else from the first .env that has
    it. An exported value wins, as in pipeline/config.py."""
    key = os.environ.get("NVIDIA_API_KEY", "").strip()
    for path in ENV_FILES:
        if key or not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            name, sep, value = line.partition("=")
            if sep and name.strip() == "NVIDIA_API_KEY":
                key = value.strip().strip("'\"")
    if not key:
        raise SystemExit("NVIDIA_API_KEY is not set: export it or put it in Src/source/pipeline/.env")
    return key


def ask_teacher(record: dict[str, Any], key: str, model: str = MODEL) -> str:
    """The teacher's reply text for one record. Retries rate limits, server
    errors and dropped connections with a back-off."""
    body = json.dumps({
        "model": model,
        "messages": cp.build_messages(record["source"], record["signals"], few_shot=True),
        "temperature": TEMPERATURE,
        "max_tokens": MAX_TOKENS,
    }).encode("utf-8")
    problem = ""
    for wait in (*BACKOFF, None):
        request = urllib.request.Request(URL, data=body, headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                reply = json.loads(response.read().decode("utf-8"))
            return reply["choices"][0]["message"].get("content") or ""
        except urllib.error.HTTPError as exc:
            if exc.code not in RETRY_CODES:
                raise TeacherConfigError(f"HTTP {exc.code} from {URL} for model {model}") from None
            problem = f"HTTP {exc.code}"
        except (http.client.HTTPException, OSError) as exc:     # timeouts, resets, cut-off bodies
            problem = type(exc).__name__
        except (KeyError, IndexError, TypeError, ValueError):
            problem = "unexpected response shape"
        if wait is None:
            break
        time.sleep(wait)
    raise TeacherError(f"no answer after {len(BACKOFF) + 1} tries ({problem})")


def to_record(record: dict[str, Any], reply: str, model: str) -> dict[str, Any]:
    """What gets written: the parsed answer, or the reply under `raw` if it
    isn't usable."""
    out = {k: record[k] for k in ("id", "dataset", "source", "signals")}
    try:
        out.update(cp.parse_response(reply))
    except cp.ComposeOutputError:
        out["raw"] = reply
    out["model"] = model
    out["prompt_version"] = cp.fingerprint()
    return out


def io_paths(dataset: str, gold: bool, root: Path = ROOT) -> tuple[Path, Path]:
    if gold:
        return (root / "data" / "gold" / f"{dataset}_gold.jsonl",
                root / "data" / "gold_drafts" / f"{dataset}_gold_draft.jsonl")
    return (root / "data" / "source" / f"{dataset}_source.jsonl",
            root / "data" / "generated" / f"{dataset}_gen.jsonl")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue        # a line cut off by a crash; that id just gets redone
    return rows


def run(dataset: str, *, gold: bool = False, limit: int = 0, workers: int = 5, model: str = MODEL,
        root: Path = ROOT, ask: Callable[[dict[str, Any]], str] | None = None) -> dict[str, int]:
    """Generate one dataset. Returns counts: written, raw, failed, skipped."""
    src_path, out_path = io_paths(dataset, gold, root)
    if not src_path.is_file():
        print(f"{dataset}: {src_path.relative_to(root)} doesn't exist yet, skipped")
        return {"written": 0, "raw": 0, "failed": 0, "skipped": 0}
    records = read_jsonl(src_path)
    done = {r.get("id") for r in read_jsonl(out_path)} if out_path.is_file() else set()
    no_signals = [r for r in records if not r.get("signals")]
    todo = [r for r in records if r.get("signals") and r["id"] not in done]
    if limit:
        todo = todo[:limit]
    if no_signals:
        print(f"{dataset}: {len(no_signals)} records have no signals yet, skipped "
              f"(they come from the step-1 script, run on the frozen adapters)")
    print(f"{dataset}: {len(done)} already done, {len(todo)} to go -> {out_path.relative_to(root)}")
    if not todo:
        return {"written": 0, "raw": 0, "failed": 0, "skipped": len(no_signals)}

    if ask is None:
        key = api_key()
        ask = lambda r: ask_teacher(r, key, model)  # noqa: E731
    out_path.parent.mkdir(parents=True, exist_ok=True)
    counts = {"written": 0, "raw": 0, "failed": 0, "skipped": len(no_signals)}
    lock, stop = threading.Lock(), threading.Event()
    stopped_by: list[str] = []
    started = time.time()

    with out_path.open("a", encoding="utf-8") as out:
        def one(record: dict[str, Any]) -> None:
            if stop.is_set():
                return
            try:
                reply = ask(record)
            except TeacherConfigError as exc:
                stopped_by.append(str(exc))
                stop.set()
                return
            except TeacherError as exc:
                with lock:
                    counts["failed"] += 1
                    print(f"  {record['id']}: {exc}")
                return
            row = to_record(record, reply, model)
            with lock:
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                out.flush()
                counts["written"] += 1
                counts["raw"] += "raw" in row
                n = counts["written"] + counts["failed"]
                if n % 25 == 0 or n == len(todo):
                    rate = n / max(time.time() - started, 1e-9) * 60
                    left = (len(todo) - n) / rate if rate else 0
                    print(f"  {dataset}: {n}/{len(todo)} ({counts['raw']} unusable, {counts['failed']} "
                          f"no answer)  {rate:.1f}/min  ~{left:.0f} min left", flush=True)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            try:
                list(pool.map(one, todo))
            except KeyboardInterrupt:
                stop.set()      # queued records return at once; requests in flight finish and are kept
                print("\nstopping after the requests in flight. Run the same command to carry on.")
                raise

    if stopped_by:
        raise SystemExit(f"stopped: {stopped_by[0]}. Nothing is wrong with the data; fix the key "
                         f"or model and run the same command again.")
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("datasets", nargs="+", choices=DATASETS)
    ap.add_argument("--gold", action="store_true", help="draft gold rewrites into data/gold_drafts/")
    ap.add_argument("--limit", type=int, default=0, help="only this many new records per dataset")
    ap.add_argument("--workers", type=int, default=5, help="requests in parallel")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args(argv)

    print(f"teacher {args.model}, prompt {cp.PROMPT_VERSION} {cp.fingerprint()}")
    failed = 0
    for dataset in args.datasets:
        counts = run(dataset, gold=args.gold, limit=args.limit, workers=args.workers, model=args.model)
        failed += counts["failed"]
        print(f"{dataset}: wrote {counts['written']} ({counts['raw']} unusable, kept for the filter), "
              f"{counts['failed']} got no answer")
    if failed:
        print(f"\n{failed} records got no answer. Run the same command again to retry just those.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
