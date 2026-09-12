# enron_evaluate_and_predict.py
# macro f1 + confusion matrix on the 300 held out rows, correlation check
# against yvonne's politeness scores, and the predict() output everyone
# in the fusion layer uses.

from pathlib import Path
import torch
import pandas as pd
from scipy.stats import pearsonr
from sklearn.metrics import f1_score, confusion_matrix, classification_report
from transformers import AutoTokenizer, AutoModelForSequenceClassification

MODEL_DIR = Path("models/enron_tone_distilbert")
EVAL_HUMAN_FILE = Path("data/processed/enron_tone_eval_human.csv")
STANFORD_FILE = Path("data/processed/stanford_politeness_output.csv")

LABELS = ["neutral", "casual", "terse"]  # formal merged into neutral
LABEL2SCORE = {"neutral": 0.55, "casual": 0.3, "terse": 0.15}

_model, _tok = None, None


def _load():
    global _model, _tok
    if _model is None:
        _tok = AutoTokenizer.from_pretrained(str(MODEL_DIR))
        _model = AutoModelForSequenceClassification.from_pretrained(str(MODEL_DIR))
        _model.eval()
    return _model, _tok


def build_note(body, label):
    wc = len(body.split())
    has_signoff = any(s in body.lower()[-60:] for s in ["regards", "thanks", "best", "sincerely"])
    if label == "terse":
        return f"no greeting, no sign-off, {wc} words"
    if label == "casual":
        return "fragments or slang, minimal greeting"
    return "standard business tone"


def predict(body):
    model, tok = _load()
    inputs = tok(body, truncation=True, max_length=256, padding=True, return_tensors="pt")
    with torch.no_grad():
        logits = model(**inputs).logits
    probs = torch.softmax(logits, dim=-1)[0]
    pred_id = int(torch.argmax(probs))
    label = LABELS[pred_id]
    return {
        "model": "tone",
        "label": label,
        "confidence": round(float(probs[pred_id]), 2),
        "note": build_note(body, label),
    }


def evaluate():
    if not EVAL_HUMAN_FILE.exists():
        print("need the hand-labelled eval file first")
        return None
    df = pd.read_csv(EVAL_HUMAN_FILE)
    if "human_label" not in df.columns:
        print("no human_label column")
        return None

    df["predicted_label"] = [predict(b)["label"] for b in df["body"]]

    macro_f1 = f1_score(df["human_label"], df["predicted_label"], average="macro", labels=LABELS)
    print(f"macro f1: {macro_f1:.3f}")
    print(classification_report(df["human_label"], df["predicted_label"], labels=LABELS, zero_division=0))

    cm = confusion_matrix(df["human_label"], df["predicted_label"], labels=LABELS)
    print(pd.DataFrame(cm, index=LABELS, columns=LABELS))

    fi, ni = LABELS.index("formal"), LABELS.index("neutral")
    confusion_pct = (cm[fi][ni] + cm[ni][fi]) / cm.sum() if cm.sum() else 0
    if confusion_pct > 0.15:
        print("formal/neutral getting mixed up a lot - might be worth merging into 3 classes")

    return df


def correlation_check(tone_df):
    if not STANFORD_FILE.exists():
        print(f"no {STANFORD_FILE} yet, skipping correlation check")
        return
    stanford_df = pd.read_csv(STANFORD_FILE)
    merged = tone_df.merge(stanford_df, on="body", how="inner")
    if merged.empty:
        print("no overlap between tone eval and stanford output")
        return

    tone_scores = merged["predicted_label"].map(LABEL2SCORE)
    politeness_scores = merged["politeness_score"]
    corr, p = pearsonr(tone_scores, politeness_scores)
    print(f"\ntone vs politeness correlation (n={len(merged)}): r={corr:.3f}, p={p:.4f}")
    if abs(corr) > 0.7:
        print("high correlation - might not be as orthogonal as we wanted, flag to team")


def main():
    df = evaluate()
    if df is not None:
        correlation_check(df)


if __name__ == "__main__":
    main()