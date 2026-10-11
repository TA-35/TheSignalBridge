"""Hedged and rough-notes inputs for run 2, derived from real source messages.

Run 1 had almost no hedged requests (34 of 1,873 training pairs had any hedge
phrase; 3 had "no rush" or "when you get a chance") and no rough notes at
all, and it showed: it kept hedges and didn't turn notes into a message. Both
are core cases for Compose - dictated input arrives as notes.

Each variant starts from a real request in data/source (already PII-scrubbed,
never gold; picked from those whose teacher reading has an ask). The teacher
rewrites it as

    hedges   the same request from a colleague who softens everything
             ("no rush, but if you get a chance could you maybe ...")
    notes    the rough notes or dictation the sender might start from
             ("tell priya demo moved to 3, bring laptop")

The variant is then the source of a normal pair: generate_pairs.py writes its
rewrite with the shared prompt and filter_pairs.py checks it like any other.

    python Src/source/data_prep/make_variants.py hedges --n 300
    python Src/source/data_prep/make_variants.py notes --n 300
        -> data/source/<kind>_source.jsonl   (id, dataset, source, signals, origin)
    python Src/source/data_prep/generate_pairs.py hedges notes

A variant may never add a name, number or date; a hedged one must also keep
every one it started with. Signals come from the frozen adapters, on the
variant itself. The two kinds never share a source message, and a re-run
keeps what's already written.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from Src.source.data_prep import filter_pairs as fp  # noqa: E402
from Src.source.data_prep import flag_rule as fr  # noqa: E402
from Src.source.data_prep import generate_pairs as gp  # noqa: E402

SEED = 42
KINDS = ("hedges", "notes")
POOLS = ("enron", "stanford")
MIN_WORDS, MAX_WORDS = 8, 70
TEMPERATURE = 0.8       # variety in how people hedge and take notes

KEEP = ("Keep every name, number, date, time, amount and placeholder (like [PHONE_REDACTED] or [URL]) "
        "exactly as written, and don't add any new ones.")

INSTRUCTIONS = {
    "hedges": (
        "Rewrite this workplace message the way a colleague who softens everything would write it, so the "
        "real request is buried. Use two or three hedges, and vary them: \"no rush, but\", \"if you get a "
        "chance\", \"when you have a sec\", \"just wondering if\", \"might be worth\", \"would be great if\", "
        "\"maybe\", \"I was thinking maybe\", \"whenever suits\". Keep the same request and the same people. "
        "If there is a deadline, keep it, even if you soften how it's said. Keep the register: casual stays "
        f"casual. {KEEP}\n\nReturn JSON only: {{\"message\": \"...\"}}"),
    "notes": (
        "Rewrite this workplace message as the rough notes its sender might type or dictate before writing "
        "it properly. Pick one style: (a) typed notes: lowercase, no greeting or sign-off, shorthand, missing "
        "words (\"need q3 numbers b4 thurs mtg\"); (b) dictated: one run-on sentence, no punctuation, filler "
        "like \"um\" or \"so basically\"; (c) a note to self naming who it's for (\"tell sam ...\", \"ask "
        f"priya to ...\"). Keep the request and any deadline. {KEEP}\n\n"
        "Return JSON only: {\"message\": \"...\", \"style\": \"typed\" or \"dictated\" or \"note_to_self\"}"),
}


def candidates(root: Path = ROOT) -> dict[str, list[dict[str, Any]]]:
    """Source requests per pool, in a fixed order: the teacher's reading of them
    has an ask, they're 8-70 words, and none is close to a gold message."""
    _, gold = fp.gold_index()
    out = {}
    for pool in POOLS:
        gen_path = root / "data" / "generated" / f"{pool}_gen.jsonl"
        rows = [json.loads(l) for l in gen_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        out[pool] = [r for r in rows
                     if "rewrite" in r and r["meaning"]["ask"].strip()
                     and MIN_WORDS <= len(r["source"].split()) <= MAX_WORDS
                     and not fp.near_gold(r["source"], gold)]
    return out


def pick(cands: dict[str, list[dict[str, Any]]], kind: str, n: int) -> list[dict[str, Any]]:
    """n originals for this kind, split evenly across the pools. hedges take the
    front of each shuffled pool and notes the back, so they never overlap."""
    chosen = []
    for pool in POOLS:
        rows = list(cands[pool])
        random.Random(SEED).shuffle(rows)
        half = len(rows) // 2
        side = rows[:half] if kind == "hedges" else rows[half:]
        chosen += side[: n // len(POOLS)]
    return chosen


def parse(reply: str) -> dict[str, Any] | None:
    match = re.search(r"\{.*\}", reply, re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data.get("message"), str) and data["message"].strip() else None


def problem(kind: str, original: str, variant: str) -> str | None:
    """Why a variant can't be used, or None."""
    if variant.strip() == original.strip():
        return "unchanged"
    pair = {"source": original, "rewrite": variant}
    if fp.check_added(pair):
        return "added an entity"
    if kind == "hedges":
        if fp.check_dropped(pair):
            return "dropped an entity"
        if len(variant.split()) < len(original.split()):
            return "shorter than the original"
    elif len(variant.split()) > len(original.split()) * 1.2:
        return "longer than the original"
    return None


def run(kind: str, n: int, *, workers: int = 8, root: Path = ROOT,
        ask: Callable[[list[dict[str, str]]], str] | None = None,
        signals: Callable[[str], list[dict[str, Any]]] | None = None) -> dict[str, int]:
    out_path = root / "data" / "source" / f"{kind}_source.jsonl"
    done = {}
    if out_path.is_file():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["origin"]] = rec
    todo = [r for r in pick(candidates(root), kind, n) if r["id"] not in done]
    print(f"{kind}: {len(done)} already written, {len(todo)} to make")
    if ask is None:
        key = gp.api_key()
        ask = lambda messages: gp.chat(messages, key, temperature=TEMPERATURE)  # noqa: E731
    signals = signals or fr.compute_signals

    made, rejected, lock = [], {}, threading.Lock()

    def one(original: dict[str, Any]) -> None:
        messages = [{"role": "system", "content": INSTRUCTIONS[kind]},
                    {"role": "user", "content": original["source"]}]
        try:
            data = parse(ask(messages))
        except gp.TeacherError:
            data = None
        why = "no usable reply" if data is None else problem(kind, original["source"], data["message"])
        with lock:
            if why:
                rejected[why] = rejected.get(why, 0) + 1
            else:
                made.append((original, data))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, todo))

    # Adapters run here, one at a time: they aren't known to be thread-safe.
    start = len(done)
    rows = []
    for i, (original, data) in enumerate(sorted(made, key=lambda m: m[0]["id"]), start + 1):
        rec = {"id": f"{kind}_{i:05d}", "dataset": kind, "source": data["message"].strip(),
               "signals": signals(data["message"].strip()), "origin": original["id"]}
        if kind == "notes" and data.get("style") in ("typed", "dictated", "note_to_self"):
            rec["style"] = data["style"]
        rows.append(rec)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as out:
        for rec in rows:
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"{kind}: wrote {len(rows)}, rejected {sum(rejected.values())} {rejected or ''}")
    return {"written": len(rows), "rejected": sum(rejected.values())}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("kind", choices=KINDS)
    ap.add_argument("--n", type=int, default=300, help="originals to try (split evenly across pools)")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args(argv)
    run(args.kind, args.n, workers=args.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
