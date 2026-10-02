# remap_formal_to_neutral.py
# one-time fix: your 300 hand labels still have "formal" as its own class.
# since formal got merged into neutral (rules couldn't reliably separate
# them - 15/19 human-formal rows were falling through to neutral anyway),
# this remaps any "formal" human labels to "neutral" so the eval file
# matches the new 3-class scheme before you rerun the agreement check.
#
# run once: python3 remap_formal_to_neutral.py

import pandas as pd
from pathlib import Path

FILE = Path("data/processed/enron_tone_eval_human.csv")

df = pd.read_csv(FILE)

before_counts = df["human_label"].value_counts()
print("before remap:")
print(before_counts)

formal_count = (df["human_label"] == "formal").sum()
df["human_label"] = df["human_label"].replace("formal", "neutral")

print(f"\nremapped {formal_count} 'formal' rows to 'neutral'")
print("\nafter remap:")
print(df["human_label"].value_counts())

df.to_csv(FILE, index=False)
print(f"\nsaved to {FILE}")
