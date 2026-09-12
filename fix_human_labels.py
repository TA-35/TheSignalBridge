# fix_human_labels.py
# one-time fix: numbers exported the column as "Human_Label" with
# capitalized values ("Neutral", "Casual" etc) - this renames the column
# to human_label and lowercases the values so it matches what
# enron_agreement_check.py expects.
#
# run once: python3 fix_human_labels.py

import pandas as pd
from pathlib import Path

FILE = Path("data/processed/enron_tone_eval_human.csv")

df = pd.read_csv(FILE)

print("columns found:", list(df.columns))

# find whatever the label column is actually called - handles
# Human_Label, HUMAN_LABEL, Human_label, etc
label_col = None
for col in df.columns:
    if col.strip().lower() == "human_label":
        label_col = col
        break

if label_col is None:
    print("couldn't find a label column - here's what's there:")
    print(df.columns.tolist())
else:
    if label_col != "human_label":
        df = df.rename(columns={label_col: "human_label"})
        print(f"renamed '{label_col}' -> 'human_label'")

    df["human_label"] = df["human_label"].astype(str).str.strip().str.lower()

    print("\nvalue counts after lowercasing:")
    print(df["human_label"].value_counts())

    df.to_csv(FILE, index=False)
    print(f"\nfixed and saved to {FILE}")
