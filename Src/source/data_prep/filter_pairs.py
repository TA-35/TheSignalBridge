"""
filter_pairs.py
Day 2 shared filter (owner: Amulya). Reads every data/generated/*_gen.jsonl,
runs each rewrite pair through the checks from the how-to guide in order,
and rejects at the first failure.

  passing pairs -> data/filtered/train.jsonl
  rejected pairs -> data/filtered/rejects.jsonl  (with the check + reason)
  per-check counts -> data/filtered/filter_report.json  (post these in the chat)

Checks, in order:
  0. gold_overlap   - source is a gold message or a near copy of one (never train on gold)
  1. json_valid     - has rewrite, notes and meaning
  2. notes_ok       - 1-3 notes, each under 20 words
  3. dropped_entity - every PERSON/ORG/DATE/TIME/MONEY/number in the source is in the rewrite
  4. added_entity   - nothing in the rewrite that isn't in the source
  5. length         - rewrite is 0.5-2.5x the source word count
  6. contradiction  - NLI (cross-encoder/nli-deberta-v3-base) doesn't say it contradicts

Run from the repo root:
  python Src/source/data_prep/filter_pairs.py fake --n 60     # make test pairs from the source files
  python Src/source/data_prep/filter_pairs.py filter          # the real run
  python Src/source/data_prep/filter_pairs.py spotcheck       # 10% sample split three ways

Needs: spacy (en_core_web_sm), datasketch, sentence-transformers, pandas
"""

import argparse
import glob
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

GEN_GLOB = "data/generated/*_gen.jsonl"
GOLD_GLOB = "data/gold/*_gold.jsonl"
SOURCE_GLOB = "data/source/*_source.jsonl"
OUT_DIR = Path("data/filtered")
TRAIN = OUT_DIR / "train.jsonl"
REJECTS = OUT_DIR / "rejects.jsonl"
REPORT = OUT_DIR / "filter_report.json"

CHECKS = ["gold_overlap", "json_valid", "notes_ok", "dropped_entity",
          "added_entity", "length", "contradiction"]
ENT_TYPES = {"PERSON", "ORG", "DATE", "TIME", "MONEY"}
NLI_MODEL = "cross-encoder/nli-deberta-v3-base"
SEED = 42


# ---------------------------------------------------------------- io
def read_jsonl(path):
    rows = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"_raw_line": line})
    return rows


def write_jsonl(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- normalising
# "Thursday" vs "Thurs" style variants were flagged in the guide as a known
# false-rejection source, so both texts get mapped to full names before comparing
ABBREV = {
    r"mon": "monday", r"tues?": "tuesday", r"weds?": "wednesday",
    r"thu(?:rs?)?": "thursday", r"fri": "friday", r"sat": "saturday",
    r"jan": "january", r"feb": "february", r"mar": "march", r"apr": "april",
    r"jun": "june", r"jul": "july", r"aug": "august", r"sept?": "september",
    r"oct": "october", r"nov": "november", r"dec": "december",
}
ABBREV_RE = [(re.compile(rf"\b{k}\b\.?", re.I), v) for k, v in ABBREV.items()]


def norm(text):
    t = str(text).lower().replace("\u2019", "'").replace("\u2018", "'")
    for rx, full in ABBREV_RE:
        t = rx.sub(full, t)
    t = re.sub(r"'s\b", "", t)                     # Friday's -> Friday
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)      # 1,000 -> 1000
    return re.sub(r"\s+", " ", t).strip()


def tokens(text):
    return set(re.findall(r"[a-z0-9$%.:/\[\]_]+", norm(text)))


STOP = {"the", "a", "an", "of", "this", "that", "next", "last", "by", "on", "in",
        "at", "to", "and", "or", "for", "end", "week", "day", "morning",
        "afternoon", "evening", "tonight", "today", "tomorrow"}


def text_hash(t):
    t = re.sub(r"[^\w\s]", "", str(t).lower())
    return hashlib.sha1(re.sub(r"\s+", " ", t).strip().encode()).hexdigest()


# ---------------------------------------------------------------- entities
_nlp = None


def nlp():
    global _nlp
    if _nlp is None:
        import spacy
        _nlp = spacy.load("en_core_web_sm")
    return _nlp


NUM_RE = re.compile(r"\$?\d+(?:[.,:/]\d+)*%?")
PLACEHOLDER_RE = re.compile(r"\[[A-Z_]+\]")


def entities(text):
    """Things that must survive the rewrite: named entities + any number + redaction tags."""
    found = set()
    for e in nlp()(str(text)).ents:
        if e.label_ in ENT_TYPES:
            found.add(e.text.strip())
    for m in NUM_RE.findall(str(text)):
        found.add(m.rstrip(".,"))
    for m in PLACEHOLDER_RE.findall(str(text)):
        found.add(m)
    return {f for f in found if f}


def present(ent, other_text, other_norm, other_tokens):
    """An entity counts as present if its normalised text appears, or (for
    multi-word ones) all its content words do. Keeps reworded dates like
    'Friday's meeting' vs 'the meeting on Friday' from being false rejections."""
    e = norm(ent)
    if not e:
        return True
    if e in other_norm:
        return True
    words = [w for w in tokens(ent) if w not in STOP]
    return bool(words) and all(w in other_tokens for w in words)


# ---------------------------------------------------------------- record parsing
def unpack(rec):
    """Accept either a flat record (rewrite/notes/meaning at top level) or one
    where the LLM reply is still a string under raw/output/response/reply."""
    out = dict(rec)
    for key in ("raw", "output", "response", "reply", "completion"):
        if key in rec and isinstance(rec[key], str) and "rewrite" not in rec:
            s = re.sub(r"```(?:json)?", "", rec[key]).strip()
            m = re.search(r"\{.*\}", s, re.S)
            if not m:
                return out, "reply isn't JSON"
            try:
                out.update(json.loads(m.group(0)))
            except json.JSONDecodeError as e:
                return out, f"reply isn't valid JSON ({e.msg})"
    if "_raw_line" in rec:
        return out, "line in the generated file isn't valid JSON"
    return out, None


# ---------------------------------------------------------------- checks
def check_json(r):
    if not isinstance(r.get("rewrite"), str) or not r["rewrite"].strip():
        return "missing or empty rewrite"
    if not isinstance(r.get("notes"), list):
        return "notes missing or not a list"
    if not isinstance(r.get("meaning"), dict):
        return "meaning missing or not an object"
    return None


def check_notes(r):
    notes = r["notes"]
    if not 1 <= len(notes) <= 3:
        return f"{len(notes)} notes (need 1-3)"
    for n in notes:
        if not isinstance(n, str) or not n.strip():
            return "empty note"
        if len(n.split()) >= 20:
            return f"note has {len(n.split())} words (need under 20): {n[:60]}"
    return None


def check_dropped(r):
    src, rw = r["source"], r["rewrite"]
    rw_n, rw_t = norm(rw), tokens(rw)
    missing = [e for e in entities(src) if not present(e, rw, rw_n, rw_t)]
    return f"dropped {missing}" if missing else None


def check_added(r):
    src, rw = r["source"], r["rewrite"]
    src_n, src_t = norm(src), tokens(src)
    extra = [e for e in entities(rw) if not present(e, src, src_n, src_t)]
    return f"added {extra}" if extra else None


def check_length(r):
    s, w = len(str(r["source"]).split()), len(r["rewrite"].split())
    ratio = w / max(s, 1)
    if not 0.5 <= ratio <= 2.5:
        return f"length ratio {ratio:.2f} ({w} vs {s} words)"
    return None


# ---------------------------------------------------------------- gold guard
def gold_index():
    from datasketch import MinHash, MinHashLSH
    lsh = MinHashLSH(threshold=0.85, num_perm=128)
    hashes = set()
    n = 0
    for path in glob.glob(GOLD_GLOB):
        for i, g in enumerate(read_jsonl(path)):
            src = g.get("source", "")
            hashes.add(text_hash(src))
            lsh.insert(f"{path}:{i}", minhash(src))
            n += 1
    return hashes, lsh, n


def minhash(t):
    from datasketch import MinHash
    m = MinHash(num_perm=128)
    t = re.sub(r"\s+", " ", str(t).lower())
    for i in range(max(1, len(t) - 4)):
        m.update(t[i:i + 5].encode())
    return m


# ---------------------------------------------------------------- main filter
def step_filter(a):
    files = sorted(glob.glob(GEN_GLOB))
    if not files:
        raise SystemExit(f"no files match {GEN_GLOB} - has the generation script run yet?")

    gold_hashes, gold_lsh, n_gold = gold_index()
    print(f"gold messages loaded for the overlap check: {n_gold}")

    passed, rejected = [], []
    fails = Counter()
    seen = Counter()
    per_dataset = Counter()

    pending_nli = []
    for path in files:
        rows = read_jsonl(path)
        print(f"{path}: {len(rows):,} records")
        for rec in rows:
            r, parse_err = unpack(rec)
            ds = r.get("dataset", Path(path).stem.replace("_gen", ""))
            r["dataset"] = ds
            per_dataset[ds] += 1

            def reject(check, why):
                fails[check] += 1
                rejected.append({"id": r.get("id"), "dataset": ds, "check": check,
                                 "reason": why, "record": rec})

            seen["gold_overlap"] += 1
            src = r.get("source", "")
            if text_hash(src) in gold_hashes or gold_lsh.query(minhash(src)):
                reject("gold_overlap", "source is a gold message or a near copy of one")
                continue

            seen["json_valid"] += 1
            why = parse_err or check_json(r)
            if why:
                reject("json_valid", why); continue

            failed = False
            for name, fn in [("notes_ok", check_notes), ("dropped_entity", check_dropped),
                             ("added_entity", check_added), ("length", check_length)]:
                seen[name] += 1
                why = fn(r)
                if why:
                    reject(name, why); failed = True; break
            if failed:
                continue
            pending_nli.append((r, rec))

    # NLI last, in batches - it's the slow one
    seen["contradiction"] += len(pending_nli)
    if pending_nli and not a.no_nli:
        verdicts = nli_contradicts([(r["source"], r["rewrite"]) for r, _ in pending_nli])
    else:
        verdicts = [False] * len(pending_nli)
        if a.no_nli:
            print("skipping the NLI check (--no-nli)")
    for (r, rec), bad in zip(pending_nli, verdicts):
        if bad:
            fails["contradiction"] += 1
            rejected.append({"id": r.get("id"), "dataset": r["dataset"], "check": "contradiction",
                             "reason": "NLI says the rewrite contradicts the source", "record": rec})
        else:
            keep = {k: r[k] for k in ("id", "dataset", "source", "signals", "meaning",
                                       "rewrite", "notes") if k in r}
            for k in ("model", "prompt_version"):      # kept for the GenAI disclosure
                if k in r:
                    keep[k] = r[k]
            passed.append(keep)

    write_jsonl(passed, TRAIN)
    write_jsonl(rejected, REJECTS)

    total = sum(per_dataset.values())
    report = {
        "total": total, "passed": len(passed), "rejected": len(rejected),
        "per_dataset_in": dict(per_dataset),
        "per_dataset_passed": dict(Counter(p["dataset"] for p in passed)),
        "rejected_by_check": {c: fails[c] for c in CHECKS},
        "reject_rate_of_pairs_reaching_check": {
            c: round(fails[c] / seen[c], 3) if seen[c] else 0.0 for c in CHECKS},
        "nli_skipped": bool(a.no_nli),
    }
    json.dump(report, open(REPORT, "w"), indent=2)

    print(f"\npassed {len(passed):,} / {total:,}  ->  {TRAIN}")
    print(f"rejected {len(rejected):,}  ->  {REJECTS}\n")
    print(f"{'check':<16}{'rejected':>9}{'reached':>9}{'rate':>8}")
    for c in CHECKS:
        rate = fails[c] / seen[c] if seen[c] else 0
        flag = "  <- check the prompt" if seen[c] and rate > 0.3 else ""
        print(f"{c:<16}{fails[c]:>9}{seen[c]:>9}{rate:>8.1%}{flag}")
    if len(passed) < 2000 and not a.allow_small:
        print(f"\nheads up: under 2,000 passing pairs (guide's 'done when' target)")


def nli_contradicts(pairs, bs=32):
    from sentence_transformers import CrossEncoder
    model = CrossEncoder(NLI_MODEL)
    id2label = getattr(getattr(model, "config", None), "id2label", None) \
        or getattr(model.model.config, "id2label", None)
    labels = [id2label[i].lower() for i in range(len(id2label))] if id2label \
        else ["contradiction", "entailment", "neutral"]
    c_idx = labels.index("contradiction")
    print(f"running NLI on {len(pairs):,} pairs (labels {labels})...")
    scores = model.predict(pairs, batch_size=bs, show_progress_bar=True)
    return [int(s.argmax()) == c_idx for s in scores]


# ---------------------------------------------------------------- spot check
def step_spotcheck(a):
    import pandas as pd
    rows = read_jsonl(TRAIN)
    random.seed(SEED)
    sample = random.sample(rows, max(1, round(len(rows) * 0.10)))
    people = ["yvonne", "amulya", "anuvrat"]
    for i, who in enumerate(people):
        part = sample[i::3]
        df = pd.DataFrame([{
            "id": r["id"], "dataset": r["dataset"], "source": r["source"],
            "rewrite": r["rewrite"], "notes": " | ".join(r["notes"]),
            "pass_fail": "", "reason_if_fail": ""} for r in part])
        out = OUT_DIR / f"spotcheck_{who}.csv"
        df.to_csv(out, index=False)
        print(f"{out}: {len(df)} pairs")
    print("mark pass/fail against the style guide; over 20% fail -> fix the prompt, don't hand-edit pairs")


# ---------------------------------------------------------------- fake test data
def step_fake(a):
    """Builds data/generated/test_gen.jsonl from the real source files, with some
    pairs broken on purpose, so the filter can be tested before Yvonne's batch."""
    src = []
    for p in sorted(glob.glob(SOURCE_GLOB)):
        src += read_jsonl(p)
    if not src:
        raise SystemExit("no source files found in data/source/")
    random.seed(SEED)
    pick = random.sample(src, min(a.n, len(src)))
    out = []
    for i, s in enumerate(pick):
        text = s["source"]
        good = {"id": s["id"], "dataset": s["dataset"], "source": text,
                "signals": s.get("signals", []),
                "meaning": {"ask": "", "deadline": "", "urgency": "medium", "tone": "friendly", "implied": ""},
                "rewrite": f"To be clear: {text}",
                "notes": ["Made the ask explicit."],
                "model": "fake-test", "prompt_version": "test"}
        kind = i % 8
        if kind == 1:
            good = {**good}; good.pop("meaning")                                  # json_valid
        elif kind == 2:
            good["notes"] = ["this note is far too long " * 4]                     # notes_ok
        elif kind == 3:
            ents = sorted(entities(text), key=len, reverse=True)
            if ents:
                good["rewrite"] = good["rewrite"].replace(ents[0], "someone")     # dropped_entity
        elif kind == 4:
            good["rewrite"] += " Please reply to Bartholomew Quinnsworth by 14 March."  # added_entity
        elif kind == 5:
            good["rewrite"] = "Ok."                                               # length
        elif kind == 6:
            good = {"id": s["id"], "dataset": s["dataset"], "source": text,
                    "raw": "sorry, I can't produce JSON for this one"}            # json_valid (raw)
        out.append(good)
    path = Path("data/generated/test_gen.jsonl")
    write_jsonl(out, path)
    print(f"wrote {len(out)} test pairs -> {path}")
    print("about 1 in 4 should pass cleanly, the rest each break one check on purpose")
    print("delete it before the real run:  rm data/generated/test_gen.jsonl")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["filter", "spotcheck", "fake"])
    ap.add_argument("--n", type=int, default=60, help="fake: how many test pairs")
    ap.add_argument("--no-nli", action="store_true", help="skip the contradiction check (quick tests)")
    ap.add_argument("--allow-small", action="store_true")
    a = ap.parse_args()
    {"filter": step_filter, "spotcheck": step_spotcheck, "fake": step_fake}[a.step](a)
