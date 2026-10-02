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
    if not isinstance(body, str) or not body.strip():
        body = " "  # empty rows still need a valid string for the tokenizer
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

    # formal/neutral merge-confusion check removed - formal is already
    # merged into neutral, so LABELS.index("formal") no longer exists.
    # casual is the weak class now (recall 0.30) per the report above.

    return df


def correlation_check(tone_df):
    if not STANFORD_FILE.exists():
        print(f"no {STANFORD_FILE} yet, skipping correlation check")
        return
    stanford_df = pd.read_csv(STANFORD_FILE)
    # yvonne flagged 12 rows with blank scores (empty body on her end) -
    # drop those before correlating, pearsonr can't handle NaN
    stanford_df = stanford_df.dropna(subset=["politeness_score"])

    # some message bodies repeat (short generic ones like "fyi" show up
    # more than once) - without deduping first, an inner merge fans out
    # (2 copies matching 2 copies = 4 rows), which inflates n and can
    # break the correlation. keep first occurrence only, on both sides.
    tone_dedup = tone_df.drop_duplicates(subset="body", keep="first")
    stanford_dedup = stanford_df.drop_duplicates(subset="body", keep="first")

    merged = tone_dedup.merge(stanford_dedup, on="body", how="inner")
    if merged.empty:
        print("no overlap between tone eval and stanford output")
        return

    tone_scores = merged["predicted_label"].map(LABEL2SCORE).astype(float)
    politeness_scores = merged["politeness_score"].astype(float)

    valid = tone_scores.notna() & politeness_scores.notna()
    tone_scores, politeness_scores = tone_scores[valid], politeness_scores[valid]

    print(f"matched {len(merged)} unique messages between tone eval and stanford output")

    if tone_scores.nunique() <= 1 or politeness_scores.nunique() <= 1:
        print("one of the two score sets has zero variance in this overlap - cant compute a correlation")
        return

    corr, p = pearsonr(tone_scores, politeness_scores)
    print(f"\ntone vs politeness correlation (n={len(tone_scores)}): r={corr:.3f}, p={p:.4f}")
    if abs(corr) > 0.7:
        print("high correlation - might not be as orthogonal as we wanted, flag to team")
    else:
        print("correlation is low enough that tone and politeness look like separable signals")


def main():
    df = evaluate()
    if df is not None:
        correlation_check(df)


if __name__ == "__main__":
    main()