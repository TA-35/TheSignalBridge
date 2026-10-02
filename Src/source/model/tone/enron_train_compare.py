"""
enron_train_compare.py
Before vs after for the Decode tone model.

  BEFORE  = current DistilBERT checkpoint (66M params, rule labels, ~72% acc)
  AFTER-a = DistilBERT retrained on the ~100k auto-labelled rows   (data effect)
  AFTER-b = bigger model (roberta-base, 125M) on the same 100k rows (params effect)

Splitting it this way means we can say how much of the gain came from more
data and how much from a bigger model, instead of mixing the two up.

Everything is scored on the SAME 300-row hand-labelled gold set, so the
numbers line up with what we reported in Iteration 2.

Thresholds compared for each model:
  1. confidence sweep 0.40 -> 0.95: at each cut-off, how many messages we'd
     still answer confidently (coverage) and how accurate those are. Below
     the cut-off Decode would say "tone is unclear".
  2. per-class bias tuning on the val split, to push casual recall up
     (it was 0.30 before) without wrecking the other classes.

Outputs go to results/tone_compare/:
  summary.csv, threshold_sweep.csv, threshold_curve.png, confusion_<model>.png

Needs: pip install torch transformers scikit-learn pandas matplotlib
GPU strongly recommended for 100k rows (Colab T4 is fine).
Quick dry run: python3 enron_train_compare.py --max-train-rows 5000 --epochs 1
"""

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from sklearn.metrics import (accuracy_score, f1_score, recall_score,
                             confusion_matrix, ConfusionMatrixDisplay)
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset
from transformers import (AutoTokenizer, AutoModelForSequenceClassification,
                          Trainer, TrainingArguments)

LABELS = ["neutral", "casual", "terse"]
L2I = {l: i for i, l in enumerate(LABELS)}
DEVICE = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")
BASELINE_ORDER = "neutral,casual,terse"
THRESHOLDS = np.round(np.arange(0.40, 0.96, 0.05), 2)


# ---------------------------------------------------------------- data
class ToneDS(Dataset):
    def __init__(self, texts, labels, tok, max_len):
        self.enc = tok(list(texts), truncation=True, max_length=max_len, padding="max_length")
        self.labels = list(labels)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, i):
        item = {k: torch.tensor(v[i]) for k, v in self.enc.items()}
        item["labels"] = torch.tensor(self.labels[i])
        return item


def load_training(a):
    df = pd.read_csv(a.train_csv)
    if a.label_source == "agreed":
        # only rows where rules + LLM agree: smaller but cleaner
        df = df[df["agree"]]
        df["y"] = df["llm_label"]
    else:
        df["y"] = df["llm_label"]
        if a.min_llm_conf > 0:
            df = df[df["llm_conf"] >= a.min_llm_conf]
    df = df.dropna(subset=["text", "y"])
    df = df[df["y"].isin(LABELS)]
    if a.max_train_rows:
        df = df.sample(min(a.max_train_rows, len(df)), random_state=a.seed)
    print(f"training rows ({a.label_source}): {len(df):,}")
    print(df["y"].value_counts(normalize=True).round(3).to_string())
    tr, va = train_test_split(df, test_size=0.1, stratify=df["y"], random_state=a.seed)
    return tr, va


def load_gold(a):
    g = pd.read_csv(a.gold)
    g["y"] = g[a.gold_label_col].str.lower().replace({"formal": "neutral"})
    g = g[g["y"].isin(LABELS)]
    return g[a.gold_text_col].astype(str).tolist(), g["y"].map(L2I).values


# ---------------------------------------------------------------- training
class WeightedTrainer(Trainer):
    """Class-weighted loss, same idea as before, so casual/terse don't get ignored."""
    def __init__(self, *args, class_weights=None, **kw):
        super().__init__(*args, **kw)
        self.cw = class_weights

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        out = model(**inputs)
        loss = torch.nn.functional.cross_entropy(
            out.logits, labels, weight=self.cw.to(out.logits.device))
        return (loss, out) if return_outputs else loss


def train_model(name, base, tr, a):
    out_dir = Path(a.model_dir) / name
    tok = AutoTokenizer.from_pretrained(base)
    model = AutoModelForSequenceClassification.from_pretrained(
        base, num_labels=3, id2label=dict(enumerate(LABELS)), label2id=L2I)

    y = tr["y"].map(L2I).values
    counts = np.bincount(y, minlength=3)
    cw = torch.tensor(len(y) / (3 * np.maximum(counts, 1)), dtype=torch.float)

    args = TrainingArguments(
        output_dir=str(out_dir), num_train_epochs=a.epochs,
        per_device_train_batch_size=a.batch_size, learning_rate=a.lr,
        weight_decay=0.01, warmup_ratio=0.06, logging_steps=200,
        save_strategy="no", report_to="none", seed=a.seed,
        fp16=torch.cuda.is_available())
    trainer = WeightedTrainer(model=model, args=args, class_weights=cw,
                              train_dataset=ToneDS(tr["text"], y, tok, a.max_len))
    trainer.train()
    trainer.save_model(str(out_dir)); tok.save_pretrained(str(out_dir))
    print(f"saved {name} -> {out_dir}")
    return str(out_dir)


# ---------------------------------------------------------------- inference
@torch.no_grad()
def predict_probs(ckpt, texts, max_len, bs=64):
    tok = AutoTokenizer.from_pretrained(ckpt)
    model = AutoModelForSequenceClassification.from_pretrained(ckpt).to(DEVICE).eval()

    # old checkpoint might order labels differently, so reorder to LABELS
    id2label = {int(k): v.lower() for k, v in model.config.id2label.items()}
    id2label = {k: ("neutral" if v == "formal" else v) for k, v in id2label.items()}
    if all(lab in id2label.values() for lab in LABELS):
        order = [next(k for k, v in id2label.items() if v == lab) for lab in LABELS]
    else:
        # config only has LABEL_0/1/2, so use the order passed in --baseline-label-order
        given = [x.strip() for x in BASELINE_ORDER.split(",")]
        order = [given.index(lab) for lab in LABELS]
        print(f"  {ckpt}: no label names in config, assuming order {given}")

    probs = []
    for s in range(0, len(texts), bs):
        enc = tok(texts[s:s + bs], truncation=True, max_length=max_len,
                  padding=True, return_tensors="pt").to(DEVICE)
        p = torch.softmax(model(**enc).logits.float(), -1).cpu().numpy()
        probs.append(p[:, order])
    n_params = sum(p.numel() for p in model.parameters())
    return np.vstack(probs), n_params


def tune_bias(probs_val, y_val):
    """Grid search a log-prior offset for casual and terse on the val split.
    Returns the offsets that give the best val macro F1."""
    logp = np.log(probs_val + 1e-9)
    best = (f1_score(y_val, logp.argmax(1), average="macro"), 0.0, 0.0)
    grid = np.arange(-1.0, 2.01, 0.25)
    for bc, bt in itertools.product(grid, grid):
        pred = (logp + np.array([0, bc, bt])).argmax(1)
        f = f1_score(y_val, pred, average="macro")
        if f > best[0]:
            best = (f, bc, bt)
    return np.array([0, best[1], best[2]])


def score(y, pred):
    rec = recall_score(y, pred, labels=[0, 1, 2], average=None, zero_division=0)
    return dict(accuracy=accuracy_score(y, pred),
                macro_f1=f1_score(y, pred, average="macro", labels=[0, 1, 2], zero_division=0),
                recall_neutral=rec[0], recall_casual=rec[1], recall_terse=rec[2])


def threshold_sweep(name, probs, y):
    rows = []
    conf, pred = probs.max(1), probs.argmax(1)
    for t in THRESHOLDS:
        keep = conf >= t
        r = dict(model=name, threshold=t, coverage=keep.mean())
        if keep.sum() > 0:
            r["accuracy_kept"] = accuracy_score(y[keep], pred[keep])
            r["macro_f1_kept"] = f1_score(y[keep], pred[keep], average="macro",
                                          labels=[0, 1, 2], zero_division=0)
        rows.append(r)
    return rows


# ---------------------------------------------------------------- main
def main(a):
    global BASELINE_ORDER
    BASELINE_ORDER = a.baseline_label_order
    out = Path(a.results); out.mkdir(parents=True, exist_ok=True)
    tr, va = load_training(a)
    gold_x, gold_y = load_gold(a)
    va_x, va_y = va["text"].astype(str).tolist(), va["y"].map(L2I).values

    # name -> checkpoint path
    ckpts = {}
    if a.baseline_ckpt and Path(a.baseline_ckpt).exists():
        ckpts["before_distilbert_rules"] = a.baseline_ckpt
    else:
        print("no baseline checkpoint found, skipping BEFORE (pass --baseline-ckpt)")
    if not a.skip_small:
        ckpts["after_distilbert_100k"] = train_model("after_distilbert_100k", a.small_model, tr, a)
    ckpts[f"after_{a.big_model.split('/')[-1]}_100k"] = train_model(
        f"after_{a.big_model.split('/')[-1]}_100k", a.big_model, tr, a)

    summary, sweep = [], []
    for name, ck in ckpts.items():
        print(f"\nevaluating {name}")
        p_gold, n_params = predict_probs(ck, gold_x, a.max_len)
        p_val, _ = predict_probs(ck, va_x, a.max_len)

        # default argmax
        base = score(gold_y, p_gold.argmax(1))
        summary.append(dict(model=name, params_M=round(n_params / 1e6), setting="argmax", **base))

        # tuned per-class bias (tuned on val, applied to gold)
        bias = tune_bias(p_val, va_y)
        tuned_pred = (np.log(p_gold + 1e-9) + bias).argmax(1)
        summary.append(dict(model=name, params_M=round(n_params / 1e6),
                            setting=f"bias casual={bias[1]:+.2f} terse={bias[2]:+.2f}",
                            **score(gold_y, tuned_pred)))

        sweep += threshold_sweep(name, p_gold, gold_y)

        ConfusionMatrixDisplay(confusion_matrix(gold_y, p_gold.argmax(1), labels=[0, 1, 2]),
                               display_labels=LABELS).plot(cmap="Blues", colorbar=False)
        plt.title(name); plt.tight_layout(); plt.savefig(out / f"confusion_{name}.png", dpi=150); plt.close()

    s = pd.DataFrame(summary).round(3)
    w = pd.DataFrame(sweep).round(3)
    s.to_csv(out / "summary.csv", index=False)
    w.to_csv(out / "threshold_sweep.csv", index=False)

    fig, ax = plt.subplots(1, 2, figsize=(11, 4))
    for name, g in w.groupby("model"):
        ax[0].plot(g["threshold"], g["accuracy_kept"], marker="o", label=name)
        ax[1].plot(g["threshold"], g["coverage"], marker="o", label=name)
    ax[0].set(title="Accuracy on messages above threshold", xlabel="confidence threshold", ylabel="accuracy")
    ax[1].set(title="Coverage (share of messages answered)", xlabel="confidence threshold", ylabel="coverage")
    ax[0].legend(fontsize=8); plt.tight_layout(); plt.savefig(out / "threshold_curve.png", dpi=150)

    print("\n=== summary (gold set, 300 rows) ===")
    print(s.to_string(index=False))
    print("\n=== threshold sweep ===")
    print(w.pivot(index="threshold", columns="model", values="accuracy_kept").to_string())
    json.dump(vars(a), open(out / "run_config.json", "w"), indent=2)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--train-csv", default="data/labelled/enron_tone_100k_auto.csv")
    p.add_argument("--gold", default="data/processed/enron_tone_eval_human.csv")
    p.add_argument("--gold-text-col", default="body")
    p.add_argument("--gold-label-col", default="human_label")
    p.add_argument("--baseline-ckpt", default="models/enron_tone_distilbert")
    p.add_argument("--baseline-label-order", default="neutral,casual,terse",
                   help="only used if the old model's config has LABEL_0/1/2 instead of names")
    p.add_argument("--small-model", default="distilbert-base-uncased")
    p.add_argument("--big-model", default="roberta-base",
                   help="try microsoft/deberta-v3-base (184M) for a bigger jump")
    p.add_argument("--skip-small", action="store_true", help="only train the big model")
    p.add_argument("--label-source", choices=["llm", "agreed"], default="llm")
    p.add_argument("--min-llm-conf", type=float, default=0.0)
    p.add_argument("--max-train-rows", type=int, default=0)
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--batch-size", type=int, default=32)
    p.add_argument("--lr", type=float, default=2e-5)
    p.add_argument("--max-len", type=int, default=128)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--model-dir", default="models/tone_compare")
    p.add_argument("--results", default="results/tone_compare")
    main(p.parse_args())
