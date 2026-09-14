# enron_label.py
# rule based labelling - no api key needed.
# labels: neutral / casual / terse  (formal merged into neutral - see below)
#
# NOTE: originally 4 classes (formal/neutral/casual/terse). agreement check
# on 300 hand-labelled rows showed formal was essentially undetectable by
# rules (15/19 human-formal rows fell through to neutral anyway) - this is
# exactly the documented fallback: "if formal and neutral are constantly
# confused, merge them into three classes rather than shipping a distinction
# the model can't make." so formal folds into neutral here.
#
#   neutral - standard business tone, incl. what used to be "formal"
#              (full sentences, contractions fine, greeting/sign-off or not)
#   casual  - fragments/slang, informal phrasing
#   terse   - under ~15 words, no greeting, no sign-off, bare instruction

import re, random
from pathlib import Path
import pandas as pd

SAMPLE_FILE = Path("data/processed/enron_tone_sample_3k.csv")
LABELED_FILE = Path("data/processed/enron_tone_labeled.csv")
EVAL_UNLABELED_FILE = Path("data/processed/enron_tone_eval_unlabeled.csv")

EVAL_SIZE = 300
LABELS = ["neutral", "casual", "terse"]

TERSE_MAX_WORDS = 15

CASUAL_MARKERS = [r"\bhey\b", r"\byeah\b", r"\bgonna\b", r"\bwanna\b", r"\blol\b",
                  r"\bthx\b", r"\bomg\b", r"\bcool\b", r"\bkinda\b", r"\bhaha\b",
                  r"\bscrew it\b", r"\bwhatever\b", r"\bsorta\b", r"\bgotta\b",
                  r"\bain'?t\b", r"\by'?a'?ll\b", r"\bdunno\b", r"\bgimme\b",
                  r"\blemme\b", r"\bnah\b", r"\byep\b", r"\byup\b", r"\bmeh\b",
                  r"\bugh\b", r"\bhowdy\b", r"\byo\b", r"\bguess what\b"]

PLAIN_SIGNOFFS = [r"\bthanks\b", r"\bthank you\b", r"\bbest\b", r"\bcheers\b",
                   r"\bregards\b", r"\bsincerely\b"]
GREETING_WORDS = ["hi", "hello", "hey", "dear"]


def has_any(patterns, text):
    return any(re.search(p, text) for p in patterns)


def label_message(body):
    if not isinstance(body, str) or not body.strip():
        return "neutral"

    text = body.lower().strip()
    word_count = len(text.split())
    first_line = text[:40]
    last_chunk = text[-80:]

    # bug fix: plain substring check was matching "hi" inside "this",
    # "which", "within" etc - false positives were disqualifying real
    # terse messages. use word boundaries instead.
    has_greeting = re.search(r"\b(" + "|".join(GREETING_WORDS) + r")\b", first_line) is not None
    has_signoff = has_any(PLAIN_SIGNOFFS, last_chunk)
    contraction_count = len(re.findall(r"\b\w+'\w+\b", text))

    # terse: short, no greeting, no sign-off - bare instruction/fact
    # loosened word count vs the original 10-word cutoff
    if word_count <= TERSE_MAX_WORDS and not has_greeting and not has_signoff:
        return "terse"

    # casual: only on actual informal markers now - removed the old
    # "no greeting and under 25 words" clause, it was catching almost
    # everything short and torching casual's precision
    if has_any(CASUAL_MARKERS, text):
        return "casual"

    if word_count > 0 and (contraction_count / word_count) > 0.04:
        return "casual"

    # everything else - neutral (includes what used to be "formal")
    return "neutral"


def report_class_balance(df):
    counts = df["label"].value_counts()
    print(f"class counts (using class weights in training, not downsampling):\n{counts}")
    return df


def main():
    if not SAMPLE_FILE.exists():
        print("run enron_prep.py first")
        return

    df = pd.read_csv(SAMPLE_FILE).dropna(subset=["body"])

    random.seed(42)
    eval_idx = set(random.sample(range(len(df)), min(EVAL_SIZE, len(df))))
    eval_df = df.iloc[list(eval_idx)].reset_index(drop=True)
    train_df = df.drop(df.index[list(eval_idx)]).reset_index(drop=True)

    Path("data/processed").mkdir(parents=True, exist_ok=True)
    eval_df.to_csv(EVAL_UNLABELED_FILE, index=False)
    print(f"split out {len(eval_df)} rows for hand labelling -> {EVAL_UNLABELED_FILE}")

    print(f"rule-labelling {len(train_df)} rows...")
    train_df["label"] = train_df["body"].apply(label_message)

    report_class_balance(train_df)
    train_df.to_csv(LABELED_FILE, index=False)
    print(f"\nwritten to {LABELED_FILE} ({len(train_df)} rows, class weights applied at training time)")


if __name__ == "__main__":
    main()