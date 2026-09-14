# enron_agreement_check.py
# compares rule based labels vs hand labels on the 300 eval rows.
# if agreement < 70%, the label defs (or the rules) need fixing.

from pathlib import Path
import pandas as pd
from sklearn.metrics import confusion_matrix, classification_report
from enron_label import label_message, LABELS

EVAL_HUMAN_FILE = Path("data/processed/enron_tone_eval_human.csv")
EVAL_RULE_FILE = Path("data/processed/enron_tone_eval_rule.csv")
THRESHOLD = 0.70


def main():
    if not EVAL_HUMAN_FILE.exists():
        print(f"need {EVAL_HUMAN_FILE} first - hand label the 300 unlabeled rows, add a human_label column")
        return

    df = pd.read_csv(EVAL_HUMAN_FILE)
    if "human_label" not in df.columns:
        print("no human_label column found")
        return

    df["rule_label"] = df["body"].apply(label_message)
    df.to_csv(EVAL_RULE_FILE, index=False)

    agreement = (df["human_label"] == df["rule_label"]).mean()
    print(f"agreement: {agreement:.1%}")

    print("\nper class:")
    print(classification_report(df["human_label"], df["rule_label"], labels=LABELS, zero_division=0))

    print("confusion matrix (rows=human, cols=rule):")
    cm = confusion_matrix(df["human_label"], df["rule_label"], labels=LABELS)
    print(pd.DataFrame(cm, index=LABELS, columns=LABELS))

    if agreement < THRESHOLD:
        print(f"\nbelow {THRESHOLD:.0%} - the rules aren't matching how you actually label these, tighten them up")
    else:
        print(f"\nabove {THRESHOLD:.0%}, good to train")


if __name__ == "__main__":
    main()
