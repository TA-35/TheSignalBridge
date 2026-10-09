"""
enron_register.py
New Enron classifier for the final build: neutral / casual / formal (no terse).
casual = casual + informal merged. Labels come from Claude, not by hand.

Steps (run from the repo root):
  python3 enron_register.py prep            # ~35k clean rows, Step 1 rules
  python3 enron_register.py label --limit 200   # quick test, check the output
  python3 enron_register.py label           # label everything (resumes if stopped)
  python3 enron_register.py train           # DistilBERT, saves model + metrics
  python3 enron_register.py predict "can u send it over pls"   # sanity check

Needs: pip3 install anthropic pandas scikit-learn torch transformers
       export ANTHROPIC_API_KEY=...
"""

import argparse
import hashlib
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

LABELS = ["neutral", "casual", "formal"]
L2I = {l: i for i, l in enumerate(LABELS)}

WORK = Path("data/register")
PREP_CSV = WORK / "enron_register_pool.csv"
LABEL_JSONL = WORK / "llm_labels.jsonl"
LABELLED_CSV = WORK / "enron_register_labelled.csv"
MODEL_DIR = Path("models/enron_register_distilbert")
GOLD_HUMAN = "data/processed/enron_tone_eval_human.csv"   # kept out of training

PACK = 20          # emails per API call
MAX_CHARS = 900    # 120 words fits easily

# ---------------------------------------------------------------- cleaning
# Step 1 rules: body only, no quoted replies / forwards / signatures, 5-120 words
CUT_MARKERS = [
    r"-{2,}\s*Original Message\s*-{2,}",
    r"-{2,}\s*Forwarded by",
    r"^\s*From:\s.*$\n^\s*(Sent|To|Date):",
    r"^\s*On .{5,80} wrote:\s*$",
    r"^_{5,}\s*$",
]
CUT_RE = re.compile("|".join(CUT_MARKERS), re.I | re.M)
SIG_RE = re.compile(r"^\s*(--|__)\s*$", re.M)


def clean_body(text):
    t = str(text).replace("\r", "")
    m = CUT_RE.search(t)
    if m:
        t = t[:m.start()]                     # drop quoted reply / forward
    m = SIG_RE.search(t)
    if m:
        t = t[:m.start()]                     # drop "--" signature block
    t = "\n".join(l for l in t.split("\n") if not l.lstrip().startswith(">"))
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t).strip()
    return t


def h(t):
    return hashlib.md5(re.sub(r"\s+", " ", str(t).lower()).strip().encode()).hexdigest()


def step_prep(a):
    WORK.mkdir(parents=True, exist_ok=True)
    print("reading cleaned corpus (takes a minute)...")
    df = pd.read_csv(a.corpus, usecols=["message_id", "body", "subject"])
    df["body"] = df["body"].map(clean_body)
    df["wc"] = df["body"].str.split().str.len()
    df = df[(df["wc"] >= 5) & (df["wc"] <= 120)]
    df["h"] = df["body"].map(h)
    df = df.drop_duplicates("h")
    # dedupe threads: one message per normalised subject + first 80 chars
    subj = df["subject"].fillna("").str.lower().str.replace(r"^(re|fw|fwd)\s*:\s*", "", regex=True)
    df = df[~(subj + df["body"].str[:80].str.lower()).duplicated()]

    if Path(GOLD_HUMAN).exists():
        g = pd.read_csv(GOLD_HUMAN)
        df = df[~df["message_id"].isin(set(g["message_id"]))]
        df = df[~df["h"].isin(set(g["body"].map(clean_body).map(h)))]

    print(f"{len(df):,} clean emails with 5-120 words after dedupe")

    # lean towards casual so it isn't drowned out: use the old rule sample
    # (if it exists) to give casual-looking emails extra weight
    n = min(a.n, len(df))
    weights = np.ones(len(df))
    old = Path("data/auto_label/sample.csv")
    if old.exists():
        o = pd.read_csv(old, usecols=["message_id", "rule_label"])
        cas = set(o.loc[o["rule_label"] == "casual", "message_id"])
        weights[df["message_id"].isin(cas).values] = 3.0
    pool = df.sample(n=n, weights=weights, random_state=42).reset_index(drop=True)
    pool["row_id"] = range(len(pool))
    pool[["row_id", "message_id", "body", "wc"]].to_csv(PREP_CSV, index=False)
    print(f"saved {len(pool):,} rows -> {PREP_CSV}")


# ---------------------------------------------------------------- labelling
SYSTEM = """You label the REGISTER of short workplace emails (Enron corpus).
Pick exactly one label per email:

formal  - careful, polite business register. Full greetings and sign-offs
          ("Dear", "Kind regards"), complete sentences, no contractions or slang,
          deferential or official wording ("Please find attached", "I would appreciate").
neutral - everyday professional register. Plain and businesslike, neither stiff nor
          chatty. Short practical notes with no slang belong here.
casual  - relaxed / informal / friendly. Slang, jokes, banter, contractions in a
          chatty way, "hey", "lol", "u", emoticons, lots of exclamation marks,
          personal asides. Informal emails count as casual.

Judge only how it is written, not the topic. Short does not mean casual.
Reply with ONLY a JSON array, one object per email, in order, no prose:
[{"i": 1, "label": "neutral", "confidence": 0.8}, ...]"""


def build_msg(texts):
    return "Label these emails:\n\n" + "\n\n".join(
        f"### EMAIL {i}\n{str(t)[:MAX_CHARS]}" for i, t in enumerate(texts, 1))


def parse(raw, n):
    raw = re.sub(r"```(json)?", "", raw)
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
            i, lab = int(it["i"]) - 1, str(it["label"]).lower().strip()
            lab = "casual" if lab == "informal" else lab
            if 0 <= i < n and lab in LABELS:
                out[i] = (lab, float(it.get("confidence", 0.5)))
        except (KeyError, ValueError, TypeError):
            pass
    return out


def step_label(a):
    import os
    from anthropic import Anthropic, AuthenticationError
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key or "..." in key or not key.startswith("sk-ant-"):
        print("ANTHROPIC_API_KEY isn't set to a real key. Run:\n"
              '  export ANTHROPIC_API_KEY="your-real-key"\nthen try again.')
        return
    client = Anthropic(max_retries=8)   # SDK backs off on rate limits by itself
    try:   # one tiny call first so a bad key fails straight away
        client.messages.create(model=a.model, max_tokens=5,
                               messages=[{"role": "user", "content": "hi"}])
    except AuthenticationError:
        print("API key was rejected (401). Create a new key at console.anthropic.com "
              "and export it again.")
        return
    pool = pd.read_csv(PREP_CSV)
    if a.limit:
        pool = pool.head(a.limit)

    done = set()
    if LABEL_JSONL.exists():
        for line in open(LABEL_JSONL):
            r = json.loads(line)
            if r["label"]:
                done.add(r["row_id"])
    todo = pool[~pool["row_id"].isin(done)]
    print(f"{len(done):,} already labelled, {len(todo):,} to go")

    packs = [todo.iloc[s:s + PACK] for s in range(0, len(todo), PACK)]
    lock = threading.Lock()
    t0, finished = time.time(), 0

    def run(chunk):
        msg = client.messages.create(
            model=a.model, max_tokens=1500, system=SYSTEM,
            messages=[{"role": "user", "content": build_msg(chunk["body"].tolist())}])
        return chunk, parse(msg.content[0].text, len(chunk))

    with open(LABEL_JSONL, "a") as f, ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(run, c) for c in packs]
        for fut in as_completed(futs):
            try:
                chunk, res = fut.result()
            except Exception as e:
                print("  a pack failed, it'll be retried on the next run:", str(e)[:120])
                continue
            with lock:
                for rid, (lab, conf) in zip(chunk["row_id"], res):
                    f.write(json.dumps({"row_id": int(rid), "label": lab, "conf": conf}) + "\n")
                f.flush()
                finished += 1
                if finished % 25 == 0 or finished == len(packs):
                    rate = finished * PACK / (time.time() - t0)
                    left = (len(packs) - finished) * PACK / max(rate, 1e-6) / 60
                    print(f"  {finished}/{len(packs)} packs, ~{rate:.0f} emails/s, ~{left:.0f} min left")

    # merge everything labelled so far
    if not LABEL_JSONL.exists() or LABEL_JSONL.stat().st_size == 0:
        print("nothing labelled yet - check the errors above")
        return
    lab = pd.read_json(LABEL_JSONL, lines=True)
    if "label" not in lab.columns:
        print("nothing labelled yet - check the errors above")
        return
    lab = lab.dropna(subset=["label"])
    lab = lab.drop_duplicates("row_id", keep="last")
    full = pd.read_csv(PREP_CSV).merge(lab, on="row_id")
    full.to_csv(LABELLED_CSV, index=False)
    print(f"\n{len(full):,} labelled rows -> {LABELLED_CSV}")
    print(full["label"].value_counts().to_string())
    missing = len(pd.read_csv(PREP_CSV)) - len(full)
    if missing and not a.limit:
        print(f"{missing:,} rows still unlabelled -> just run `label` again to finish them")


# ---------------------------------------------------------------- training
def step_train(a):
    import torch
    from torch.utils.data import Dataset
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report, confusion_matrix, f1_score, accuracy_score
    from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                              Trainer, TrainingArguments)

    df = pd.read_csv(LABELLED_CSV)
    if a.min_conf:
        df = df[df["conf"] >= a.min_conf]
    df["y"] = df["label"].map(L2I)
    print(f"training on {len(df):,} rows")
    print(df["label"].value_counts().to_string())
    tr, te = train_test_split(df, test_size=0.1, stratify=df["y"], random_state=42)

    tok = AutoTokenizer.from_pretrained(a.base)
    model = AutoModelForSequenceClassification.from_pretrained(
        a.base, num_labels=3, id2label=dict(enumerate(LABELS)), label2id=L2I)

    class DS(Dataset):
        def __init__(self, d):
            self.e = tok(d["body"].astype(str).tolist(), truncation=True, max_length=128,
                         padding="max_length")
            self.y = d["y"].tolist()
        def __len__(self): return len(self.y)
        def __getitem__(self, i):
            x = {k: torch.tensor(v[i]) for k, v in self.e.items()}
            x["labels"] = torch.tensor(self.y[i]); return x

    counts = np.bincount(tr["y"], minlength=3)
    cw = torch.tensor(len(tr) / (3 * np.maximum(counts, 1)), dtype=torch.float)

    class WT(Trainer):   # class weights so casual/formal don't get ignored
        def compute_loss(self, model, inputs, return_outputs=False, **kw):
            y = inputs.pop("labels"); out = model(**inputs)
            loss = torch.nn.functional.cross_entropy(out.logits, y, weight=cw.to(out.logits.device))
            return (loss, out) if return_outputs else loss

    # newer transformers versions dropped some arguments, so only pass the
    # ones this version actually accepts
    import inspect, math
    total_steps = math.ceil(len(tr) / 32) * a.epochs
    wanted = dict(
        output_dir="models/_register_tmp", num_train_epochs=a.epochs,
        per_device_train_batch_size=32, learning_rate=3e-5, weight_decay=0.01,
        warmup_steps=int(0.06 * total_steps), logging_steps=100,
        save_strategy="no", report_to="none", fp16=torch.cuda.is_available())
    ok = set(inspect.signature(TrainingArguments.__init__).parameters)
    skipped = [k for k in wanted if k not in ok]
    if skipped:
        print("skipping args this transformers version doesn't support:", skipped)
    args = TrainingArguments(**{k: v for k, v in wanted.items() if k in ok})
    WT(model=model, args=args, train_dataset=DS(tr)).train()

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(MODEL_DIR); tok.save_pretrained(MODEL_DIR)

    # held-out test (10%, labels from Claude)
    probs = predict_probs(te["body"].astype(str).tolist())
    pred = probs.argmax(1)
    rep = classification_report(te["y"], pred, target_names=LABELS, digits=3, zero_division=0)
    cm = confusion_matrix(te["y"], pred, labels=[0, 1, 2])
    metrics = dict(rows_train=len(tr), rows_test=len(te),
                   accuracy=round(accuracy_score(te["y"], pred), 4),
                   macro_f1=round(f1_score(te["y"], pred, average="macro"), 4),
                   labels=LABELS, confusion_matrix=cm.tolist())
    json.dump(metrics, open(MODEL_DIR / "metrics.json", "w"), indent=2)
    (MODEL_DIR / "classification_report.txt").write_text(rep)
    print("\n=== held-out test (vs Claude labels) ===\n" + rep)
    print("confusion matrix (rows = true, cols = predicted):", LABELS)
    print(cm)
    print(f"\nmodel saved -> {MODEL_DIR}")


_cache = {}


def predict_probs(texts, bs=64):
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    # Not MPS. On a Mac where llama-server holds the GPU, MPS ran out of memory
    # and returned wrong labels without raising (8 of 15 flipped in a test).
    # CPU gives the same labels and takes ~12ms a message.
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    if "m" not in _cache:
        _cache["t"] = AutoTokenizer.from_pretrained(MODEL_DIR)
        _cache["m"] = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR).to(dev).eval()
    tok, model = _cache["t"], _cache["m"]
    out = []
    with torch.no_grad():
        for s in range(0, len(texts), bs):
            e = tok(texts[s:s + bs], truncation=True, max_length=128, padding=True,
                    return_tensors="pt").to(dev)
            out.append(torch.softmax(model(**e).logits.float(), -1).cpu().numpy())
    return np.vstack(out)


def classify(text):
    """What the adapter returns: label + confidence for each class."""
    p = predict_probs([clean_body(text)])[0]
    return {"tone": LABELS[int(p.argmax())],
            "tone_scores": {l: round(float(x), 3) for l, x in zip(LABELS, p)}}


# ---------------------------------------------------------------- cli
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["prep", "label", "train", "predict"])
    ap.add_argument("text", nargs="?", default="")
    ap.add_argument("--corpus", default="data/staging/enron_cleaned.csv")
    ap.add_argument("--n", type=int, default=35000)
    ap.add_argument("--limit", type=int, default=0, help="label only the first N rows (testing)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--base", default="distilbert-base-uncased")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--min-conf", type=float, default=0.0)
    a = ap.parse_args()
    if a.step == "prep": step_prep(a)
    elif a.step == "label": step_label(a)
    elif a.step == "train": step_train(a)
    else: print(json.dumps(classify(a.text), indent=2))
