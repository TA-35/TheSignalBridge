"""
pseudonymise_enron_pt14.py

PT-14 found email-like values in two of the Iteration 2 Enron files:
  data/processed/enron_tone_eval_human.csv   (1,014 unique values)
  data/processed/enron_tone_labeled.csv      (5,184 unique values)

This swaps every email-like value for a placeholder like [EMAIL_0001]. The same
address always gets the same placeholder across both files, so the text still
reads naturally and nothing about the labels changes. The placeholders have no
"@" in them, so a rescan with the PT-14 check should come back with nothing.

It catches plain addresses (jeff.dasovich@enron.com), Enron routing addresses
with the person's name in front (Mark Taylor/HOU/ECT@ECT) and short internal
forms (Sally Beck@ENRON).

The message_id column is handled differently. Those values are Enron
Message-IDs (<123.456.JavaMail.evans@thyme>), not people's addresses, and other
scripts may use them to match rows. Each one becomes msg_ plus the first 16
characters of its SHA-256 hash. That is deterministic, so if another file still
has the original IDs, running message_key() on them gives the same new key and
the rows still line up.

The mapping from real address to placeholder is never written to disk.

Run from the repo root:
  python Src/source/data_prep/pseudonymise_enron_pt14.py --check   # count only, changes nothing
  python Src/source/data_prep/pseudonymise_enron_pt14.py           # back up, rewrite, recheck
"""

import argparse
import hashlib
import re
import shutil
from pathlib import Path

import pandas as pd

FILES = [
    Path("data/processed/enron_tone_eval_human.csv"),
    Path("data/processed/enron_tone_labeled.csv"),
]
BACKUP_DIR = Path.home() / "enron_pt14_backup"  # outside the repo so it can never be committed

# "Mark Taylor/HOU/ECT@ECT", "Sally Beck@ENRON": an optional capitalised first
# name, then the routing part. Checked first so the first name goes too.
ROUTING = re.compile(r"(?:\b[A-Z][a-zA-Z'.-]+ )?\b[A-Za-z][\w'.-]*(?:/[A-Za-z0-9-]+)*@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*")
# anything else that looks like local@domain
GENERIC = re.compile(r"[^\s<>()\[\]\"',;:]+@[^\s<>()\[\]\"',;:]+")
# what counts as "email-like" when checking (same idea as the PT-14 scan)
CHECK = re.compile(r"\S+@\S+")

mapping = {}


def placeholder(value: str) -> str:
    key = value.lower().strip(".")
    if key not in mapping:
        mapping[key] = f"[EMAIL_{len(mapping) + 1:04d}]"
    return mapping[key]


def message_key(value):
    """Stable replacement for an Enron Message-ID. Same input, same output."""
    if not isinstance(value, str) or not value.strip():
        return value
    return "msg_" + hashlib.sha256(value.strip().encode("utf-8")).hexdigest()[:16]


def scrub(text):
    if not isinstance(text, str) or "@" not in text:
        return text
    text = ROUTING.sub(lambda m: placeholder(m.group(0)), text)
    return GENERIC.sub(lambda m: placeholder(m.group(0)), text)


def count_email_like(df: pd.DataFrame) -> int:
    found = set()
    for col in df.columns:
        for v in df[col].dropna().astype(str):
            found.update(CHECK.findall(v))
    return len(found)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only count email-like values")
    args = ap.parse_args()

    for f in FILES:
        if not f.exists():
            raise SystemExit(f"can't find {f}, run this from the repo root")

    if args.check:
        for f in FILES:
            df = pd.read_csv(f, dtype=str, keep_default_na=False)
            print(f"{f}: {len(df):,} rows, {count_email_like(df):,} unique email-like values")
        return

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for f in FILES:
        shutil.copy2(f, BACKUP_DIR / f.name)
    print(f"originals backed up to {BACKUP_DIR} (delete this folder once the team is happy)")

    for f in FILES:
        df = pd.read_csv(f, dtype=str, keep_default_na=False)
        before = count_email_like(df)
        text_cols = [c for c in df.columns if df[c].astype(str).str.contains("@", regex=False).any()]
        untouched = df.drop(columns=text_cols).copy()
        for c in text_cols:
            df[c] = df[c].map(message_key if c == "message_id" else scrub)
        after = count_email_like(df)

        # nothing except the scrubbed text columns is allowed to change
        assert len(df) == len(untouched), "row count changed"
        assert df.drop(columns=text_cols).equals(untouched), "a non-text column changed"

        df.to_csv(f, index=False)
        print(f"{f}: {len(df):,} rows, columns scrubbed {text_cols}, "
              f"email-like values {before:,} -> {after:,}")
        if after:
            leftovers = sorted({m for c in text_cols for v in df[c] for m in CHECK.findall(str(v))})[:10]
            print("  still email-like, check these by hand:", leftovers)

    print(f"{len(mapping):,} distinct addresses replaced (mapping kept in memory only, not saved)")


if __name__ == "__main__":
    main()
