# clean_existing_data.py
# your hand-labeled 300 and the rule-labeled 2700 both still have
# unstripped forwarding chains in the body text - that's inflating word
# counts and is very likely why terse/casual are falling through to
# neutral so often. this cleans the body text IN PLACE on the files you
# already have (does NOT re-sample or touch your hand labels), then
# refreshes the rule labels on the training set using the cleaner text.
#
# run once: python3 clean_existing_data.py
# then rerun: python3 enron_agreement_check.py

import re
from pathlib import Path
import pandas as pd

from enron_label import label_message

EVAL_HUMAN_FILE = Path("data/processed/enron_tone_eval_human.csv")
LABELED_FILE = Path("data/processed/enron_tone_labeled.csv")

# broader set of patterns than the original strip_quoted_history - covers
# the several different Enron forwarding header formats that kept showing
# up during hand-labeling (variable dash counts, "Forwarded by", manual
# "From:/To:/Subject:" blocks)
CUT_PATTERNS = [
    r"-+\s*Forwarded by.*?-+",
    r"-----Original Message-----",
    r"\nOn .{0,80} wrote:\s*\n",
    r"\n\s*From:\s.{0,80}\n\s*(Sent|To):",
    r"\n\s*To:\s.{0,200}\n\s*(cc|Subject):",
]

SIG_PATTERNS = [
    r"\n--\s*\n.*",
    r"\n\+?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\n.*",
    r"\nSent from my \w+.*",
    r"\n-{3,}\s*\nSent from.*",
]


def deep_clean(body: str) -> str:
    if not body or not isinstance(body, str):
        return body or ""

    cuts = []
    for pattern in CUT_PATTERNS:
        m = re.search(pattern, body, flags=re.IGNORECASE | re.DOTALL)
        if m:
            cuts.append(m.start())
    if cuts:
        body = body[: min(cuts)]

    for pattern in SIG_PATTERNS:
        m = re.search(pattern, body, flags=re.IGNORECASE | re.DOTALL)
        if m:
            body = body[: m.start()]

    lines = [l for l in body.split("\n") if not l.strip().startswith(">")]
    body = "\n".join(lines)

    return body.strip()


def clean_file(path: Path, relabel: bool):
    if not path.exists():
        print(f"skipping {path} - not found")
        return

    df = pd.read_csv(path)
    before_wordcounts = df["body"].astype(str).apply(lambda b: len(b.split()))

    df["body"] = df["body"].astype(str).apply(deep_clean)

    after_wordcounts = df["body"].apply(lambda b: len(b.split()))
    reduced = (before_wordcounts - after_wordcounts).clip(lower=0)
    print(f"{path.name}: avg word count {before_wordcounts.mean():.1f} -> {after_wordcounts.mean():.1f} "
          f"({(reduced > 0).sum()} rows shortened)")

    if relabel:
        old_counts = df["label"].value_counts() if "label" in df.columns else None
        df["label"] = df["body"].apply(label_message)
        print(f"  relabeled with cleaned text. new counts:\n{df['label'].value_counts()}")
        if old_counts is not None:
            print(f"  (previously:\n{old_counts})")

    df.to_csv(path, index=False)
    print(f"  saved {path}\n")


def main():
    # eval file: clean body only, NEVER touch human_label - that's your
    # hand-verified ground truth and must stay exactly as you labeled it
    clean_file(EVAL_HUMAN_FILE, relabel=False)

    # training file: clean body AND refresh the rule label, since the
    # rule depends on word count / greeting-signoff position which
    # changes once the forwarded chains are stripped
    clean_file(LABELED_FILE, relabel=True)

    print("done. now rerun: python3 enron_agreement_check.py")


if __name__ == "__main__":
    main()
