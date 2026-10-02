"""
enron_auto_label.py
Auto-labels ~1 lakh Enron emails with tone (neutral / casual / terse) so we
stop hand-writing labels.

How it works
  1. sample   -> pull ~100k rows from the full 455k cleaned corpus, balanced
                 across neutral / casual / terse (default 40/30/30), gold-set
                 rows removed so the eval stays clean
  2. calibrate-> run Claude on the 300 hand-labelled gold rows FIRST and compare
                 against the rule labeller. Cheap, and tells us whether the LLM
                 labeller is actually better before we pay for 100k rows.
  3. submit   -> send the 100k rows to Claude through the Message Batches API
                 (25 emails per request, half price vs normal calls)
  4. collect  -> poll the batches, pull results down
  5. merge    -> one CSV with rule_label, llm_label, llm_conf and an `agree`
                 flag, ready for enron_train_compare.py

Run order (from the repo root):
  python3 enron_auto_label.py sample
  python3 enron_auto_label.py calibrate
  python3 enron_auto_label.py submit
  python3 enron_auto_label.py collect     (re-run until it says all done)
  python3 enron_auto_label.py merge

Needs: pip install anthropic pandas scikit-learn
       export ANTHROPIC_API_KEY=...
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import pandas as pd

LABELS = ["neutral", "casual", "terse"]

# ---------------------------------------------------------------- paths
# change these to match the repo if they've moved
DEFAULTS = dict(
    corpus="data/staging/enron_cleaned.csv",
    gold="data/processed/enron_tone_eval_human.csv",
    work="data/auto_label",
)

PACK_SIZE = 25          # emails per API request
MAX_CHARS = 1200        # truncate long mails, tone shows up early anyway
REQS_PER_BATCH = 2000   # keep each batch job a manageable size

# ---------------------------------------------------------------- rule labeller
# Uses our existing 4-pass labeller (enron_label.py -> label_message) so the
# rule labels match what we reported in Iteration 2. If the import fails for
# some reason it falls back to a rough copy of the same rules.
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from enron_label import label_message as _label_message

    def rule_label(text):
        lab = str(_label_message(text)).lower().strip()
        return "neutral" if lab == "formal" else lab  # formal was merged into neutral
    RULES_SOURCE = "enron_label.py (label_message)"
except Exception as e:
    print(f"couldn't import enron_label.py ({e}), using fallback rules")
    RULES_SOURCE = "built-in fallback"

    GREETING = re.compile(
        r"^\s*(hi|hello|hey|dear|good (morning|afternoon|evening)|greetings)\b", re.I)
    SIGNOFF = re.compile(
        r"\b(thanks|thank you|regards|best|cheers|sincerely|thx|ta)\b[\s,!.]*([^\n]*\n?){0,2}\s*$",
        re.I)
    CASUAL = re.compile(
        r"(!{2,}|:\)|:-\)|;\)|\b(lol|haha|yeah|yep|nope|gonna|wanna|kinda|btw|cool|awesome|dude|ok cool)\b)",
        re.I)

    def rule_label(text: str) -> str:
        words = len(str(text).split())
        greet = bool(GREETING.search(text))
        sign = bool(SIGNOFF.search(text))
        if words <= 15 and not greet and not sign:
            return "terse"
        if CASUAL.search(text):
            return "casual"
        return "neutral"


# ---------------------------------------------------------------- LLM prompt
SYSTEM_PROMPT = """You label the TONE / REGISTER of workplace emails from the Enron corpus.
Pick exactly one label per email:

neutral - standard professional register. Complete sentences, normal business wording.
          Formal emails also count as neutral (we merged formal into neutral).
casual  - relaxed, friendly or chatty. Slang, jokes, exclamation marks, emoticons,
          contractions, "hey", banter, personal asides.
terse   - clipped and minimal. Very short, no greeting and no sign-off, reads as
          curt or purely transactional (e.g. "send me the file", "done.", "see below").

Judge the writer's tone only, not the topic. Ignore forwarded/quoted text if any is left.
Give a confidence between 0 and 1 for each label.

Reply with ONLY a JSON array, no prose, no code fences, one object per email, in order:
[{"i": 1, "label": "neutral", "confidence": 0.82}, ...]"""


def build_user_msg(texts):
    parts = []
    for i, t in enumerate(texts, 1):
        t = str(t)[:MAX_CHARS].strip()
        parts.append(f"### EMAIL {i}\n{t}")
    return "Label these emails:\n\n" + "\n\n".join(parts)


def parse_reply(raw, n):
    """Pull the JSON array out of the reply. Returns n (label, conf) pairs,
    with (None, None) for anything missing or broken."""
    raw = re.sub(r"```(json)?", "", raw).strip()
    m = re.search(r"\[.*\]", raw, re.S)
    out = [(None, None)] * n
    if not m:
        return out
    try:
        items = json.loads(m.group(0))
    except json.JSONDecodeError:
        return out
    for it in items:
        try:
            i = int(it["i"]) - 1
            lab = str(it["label"]).lower().strip()
            if lab == "formal":
                lab = "neutral"
            if 0 <= i < n and lab in LABELS:
                out[i] = (lab, float(it.get("confidence", 0.5)))
        except (KeyError, ValueError, TypeError):
            continue
    return out


def text_hash(t):
    return hashlib.md5(str(t).strip().lower().encode()).hexdigest()


# ---------------------------------------------------------------- steps
def step_sample(a):
    work = Path(a.work); work.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(a.corpus, usecols=lambda c: c in {a.text_col, a.id_col})
    df = df.dropna(subset=[a.text_col])
    df["h"] = df[a.text_col].map(text_hash)
    df = df.drop_duplicates("h")

    # keep the gold rows out so the 300-row eval stays unseen
    if Path(a.gold).exists():
        gold = pd.read_csv(a.gold)
        gold_h = set(gold[a.gold_text_col].map(text_hash))
        before = len(df)
        df = df[~df["h"].isin(gold_h)]
        if a.id_col in gold.columns and a.id_col in df.columns:
            df = df[~df[a.id_col].isin(set(gold[a.id_col]))]
        print(f"removed {before - len(df)} rows that overlap the gold set")

    # rule-label the whole pool first, so we can see how rare casual/terse are
    print(f"rule labeller: {RULES_SOURCE}")
    print(f"rule-labelling {len(df):,} candidate emails (takes a few minutes)...")
    df["rule_label"] = df[a.text_col].map(rule_label)
    print("tone mix in the full corpus (rule labels):")
    print(df["rule_label"].value_counts().to_string())

    # balanced sample: aim for the --mix shares so casual and terse aren't
    # drowned out by neutral. if a tone doesn't have enough emails we take all
    # of them and top up from the others.
    shares = dict(zip(LABELS, [float(x) for x in a.mix.split(",")]))
    n = min(a.n, len(df))
    target = {lab: int(round(n * shares[lab])) for lab in LABELS}
    picked, short = [], 0
    for lab in LABELS:
        pool = df[df["rule_label"] == lab]
        take = min(target[lab], len(pool))
        short += target[lab] - take
        picked.append(pool.sample(take, random_state=a.seed))
    if short > 0:
        used = pd.concat(picked).index
        rest = df.drop(used)
        picked.append(rest.sample(min(short, len(rest)), random_state=a.seed))
        print(f"not enough emails for some tones, topped up {short:,} rows from the rest")

    sample = pd.concat(picked).sample(frac=1, random_state=a.seed).reset_index(drop=True)
    sample["row_id"] = range(len(sample))
    wc = sample[a.text_col].str.split().str.len()
    sample["len_bin"] = pd.cut(wc, [0, 15, 40, 100, 250, 10**7], labels=False)

    sample[["row_id", a.id_col, a.text_col, "rule_label", "len_bin"]].to_csv(
        work / "sample.csv", index=False)
    print(f"saved {len(sample):,} rows -> {work/'sample.csv'}")
    print("tone mix in the 1 lakh sample (rule labels):")
    print(sample["rule_label"].value_counts().to_string())


def step_calibrate(a):
    """Run the LLM on the gold set with normal (non-batch) calls and compare."""
    from anthropic import Anthropic
    from sklearn.metrics import classification_report, f1_score

    client = Anthropic()
    gold = pd.read_csv(a.gold)
    gold["gold"] = gold[a.gold_label_col].str.lower().replace({"formal": "neutral"})
    texts = gold[a.gold_text_col].tolist()

    preds = []
    for s in range(0, len(texts), PACK_SIZE):
        chunk = texts[s:s + PACK_SIZE]
        msg = client.messages.create(
            model=a.model, max_tokens=2000, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_msg(chunk)}])
        preds += parse_reply(msg.content[0].text, len(chunk))
        print(f"  {min(s + PACK_SIZE, len(texts))}/{len(texts)}")

    gold["llm_label"] = [p[0] or "neutral" for p in preds]
    gold["llm_conf"] = [p[1] for p in preds]
    gold["rule_label"] = gold[a.gold_text_col].map(rule_label)
    gold.to_csv(Path(a.work) / "calibration_gold.csv", index=False)

    for name in ["rule_label", "llm_label"]:
        acc = (gold[name] == gold["gold"]).mean()
        f1 = f1_score(gold["gold"], gold[name], average="macro", labels=LABELS)
        print(f"\n=== {name}: agreement {acc:.1%}, macro F1 {f1:.3f}")
        print(classification_report(gold["gold"], gold[name], labels=LABELS, zero_division=0))

    agree = gold["rule_label"] == gold["llm_label"]
    print(f"rules and LLM agree on {agree.mean():.1%} of gold rows; "
          f"on those rows they match gold {(gold.loc[agree,'llm_label']==gold.loc[agree,'gold']).mean():.1%}")


def step_submit(a):
    from anthropic import Anthropic
    client = Anthropic()
    work = Path(a.work)
    sample = pd.read_csv(work / "sample.csv")
    texts = sample[a.text_col].tolist()
    ids = sample["row_id"].tolist()

    reqs = []
    for s in range(0, len(texts), PACK_SIZE):
        reqs.append({
            "custom_id": f"pack-{s}",   # start index, used to map results back
            "params": {
                "model": a.model, "max_tokens": 2000, "system": SYSTEM_PROMPT,
                "messages": [{"role": "user",
                              "content": build_user_msg(texts[s:s + PACK_SIZE])}],
            },
        })

    batch_ids = []
    for s in range(0, len(reqs), REQS_PER_BATCH):
        b = client.messages.batches.create(requests=reqs[s:s + REQS_PER_BATCH])
        batch_ids.append(b.id)
        print(f"submitted batch {b.id} ({len(reqs[s:s + REQS_PER_BATCH])} requests)")
    json.dump(batch_ids, open(work / "batch_ids.json", "w"), indent=2)
    print(f"{len(reqs):,} requests across {len(batch_ids)} batches. Run `collect` later.")


def step_collect(a):
    from anthropic import Anthropic
    client = Anthropic()
    work = Path(a.work)
    batch_ids = json.load(open(work / "batch_ids.json"))
    sample = pd.read_csv(work / "sample.csv")
    out_dir = work / "results"; out_dir.mkdir(exist_ok=True)

    pending = 0
    for bid in batch_ids:
        out_file = out_dir / f"{bid}.jsonl"
        if out_file.exists():
            continue
        b = client.messages.batches.retrieve(bid)
        if b.processing_status != "ended":
            pending += 1
            print(f"{bid}: still {b.processing_status} {b.request_counts}")
            continue
        rows = []
        for r in client.messages.batches.results(bid):
            start = int(r.custom_id.split("-")[1])
            n = len(sample.iloc[start:start + PACK_SIZE])
            if r.result.type == "succeeded":
                parsed = parse_reply(r.result.message.content[0].text, n)
            else:
                parsed = [(None, None)] * n
            for k, (lab, conf) in enumerate(parsed):
                rows.append({"row_id": start + k, "llm_label": lab, "llm_conf": conf})
        with open(out_file, "w") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        print(f"{bid}: saved {len(rows):,} labels")
    print("all batches collected" if pending == 0 else f"{pending} batch(es) still running, try again later")


def step_merge(a):
    work = Path(a.work)
    sample = pd.read_csv(work / "sample.csv")
    files = list((work / "results").glob("*.jsonl"))
    llm = pd.concat([pd.read_json(f, lines=True) for f in files])
    df = sample.merge(llm, on="row_id", how="left")

    missing = df["llm_label"].isna().sum()
    print(f"{missing:,} rows have no LLM label (failed/unparsed) -> dropped")
    df = df.dropna(subset=["llm_label"])
    df["agree"] = df["rule_label"] == df["llm_label"]

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.rename(columns={a.text_col: "text"})[
        ["row_id", a.id_col, "text", "rule_label", "llm_label", "llm_conf", "agree"]
    ].to_csv(out, index=False)

    print(f"saved {len(df):,} rows -> {out}")
    print(f"rules vs LLM agreement: {df['agree'].mean():.1%}")
    print("LLM label mix:\n", df["llm_label"].value_counts(normalize=True).round(3))
    print(pd.crosstab(df["rule_label"], df["llm_label"]))


# ---------------------------------------------------------------- cli
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["sample", "calibrate", "submit", "collect", "merge"])
    p.add_argument("--corpus", default=DEFAULTS["corpus"])
    p.add_argument("--gold", default=DEFAULTS["gold"])
    p.add_argument("--work", default=DEFAULTS["work"])
    p.add_argument("--out", default="data/labelled/enron_tone_100k_auto.csv")
    p.add_argument("--text-col", default="body")
    p.add_argument("--id-col", default="message_id")
    p.add_argument("--gold-text-col", default="body")
    p.add_argument("--gold-label-col", default="human_label")
    p.add_argument("--n", type=int, default=100_000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--mix", default="0.4,0.3,0.3",
                   help="target share of neutral,casual,terse in the sample")
    p.add_argument("--model", default="claude-haiku-4-5-20251001")
    a = p.parse_args()
    Path(a.work).mkdir(parents=True, exist_ok=True)
    {"sample": step_sample, "calibrate": step_calibrate, "submit": step_submit,
     "collect": step_collect, "merge": step_merge}[a.step](a)
