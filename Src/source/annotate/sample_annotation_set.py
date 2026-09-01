"""
sample_annotation_set.py

Picks the few hundred messages that actually get hand-annotated, out of
the full 455,514-row cleaned Enron set. Annotating everything would take
forever and isn't necessary - what matters is that the few hundred we
pick are a good mix, not just whichever rows happened to come first.

Stratifies by message length, a rough ambiguity heuristic, and sender
(indirectly, via shuffling), and caps how many messages come from any
one thread so a long back-and-forth doesn't dominate the sample.

Input:  data/staging/message_enron.csv, data/staging/email_meta_enron.csv
Output: data/staging/annotation_sample_v1.csv
        data/staging/annotation_sample_v1_manifest.txt
"""

import csv
import random
from pathlib import Path

csv.field_size_limit(10_000_000)

STAGING_DIR = Path("data/staging")
MESSAGE_FILE = STAGING_DIR / "message_enron.csv"
EMAIL_META_FILE = STAGING_DIR / "email_meta_enron.csv"
SAMPLE_OUTPUT = STAGING_DIR / "annotation_sample_v1.csv"
MANIFEST_OUTPUT = STAGING_DIR / "annotation_sample_v1_manifest.txt"

SAMPLE_SIZE = 400       # a few hundred, per the roadmap - not the whole dataset
MAX_PER_THREAD = 2      # stops one long thread eating a big chunk of the budget

# fixed seed so re-running this always picks the same 400 messages -
# important once annotation guidelines get built against this exact sample
RANDOM_SEED = 42

HEDGING_WORDS = ["maybe", "not sure", "let me know", "possibly", "i think",
                 "wondering", "unclear", "confused", "not certain"]


def length_bucket(char_count: int) -> str:
    if char_count < 200:
        return "short"
    elif char_count < 800:
        return "medium"
    else:
        return "long"


def looks_ambiguous(text: str) -> bool:
    # rough heuristic, not a real classifier - question marks, hedging
    # language, or being very short (under 50 chars) are decent proxies
    # for "this probably assumes context the reader doesn't have"
    text_lower = text.lower()
    if "?" in text:
        return True
    if any(word in text_lower for word in HEDGING_WORDS):
        return True
    if len(text.strip()) < 50:
        return True
    return False


def main():
    if not MESSAGE_FILE.exists() or not EMAIL_META_FILE.exists():
        print("ERROR: run build_message_table.py first.")
        return

    with open(MESSAGE_FILE, "r", encoding="utf-8", newline="") as f:
        messages = list(csv.DictReader(f))

    with open(EMAIL_META_FILE, "r", encoding="utf-8", newline="") as f:
        email_meta = {row["message_id"]: row for row in csv.DictReader(f)}

    print(f"Loaded {len(messages)} messages.")

    # tag each row with its stratification buckets up front so we're not
    # recomputing this every time we group by them later
    for row in messages:
        row["_length_bucket"] = length_bucket(int(row["char_count"]))
        row["_ambiguous"] = looks_ambiguous(row["cleaned_text"])
        meta = email_meta.get(row["message_id"], {})
        row["_sender"] = meta.get("sender", "")

    # thin out large threads before sampling - keep the first
    # MAX_PER_THREAD messages we see for each thread_id, drop the rest
    thread_counts = {}
    frame = []
    for row in messages:
        tid = row["thread_id"]
        thread_counts.setdefault(tid, 0)
        if thread_counts[tid] < MAX_PER_THREAD:
            frame.append(row)
            thread_counts[tid] += 1

    excluded_for_thread_cap = len(messages) - len(frame)
    print(f"Excluded {excluded_for_thread_cap} messages for exceeding "
          f"the {MAX_PER_THREAD}-per-thread cap.")
    print(f"Sampling frame size: {len(frame)}")

    # group into strata - one bucket per (length, ambiguous) combo.
    # sender diversity comes from shuffling within each stratum rather
    # than a separate grouping step, so no single sender clusters together
    strata = {}
    for row in frame:
        key = (row["_length_bucket"], row["_ambiguous"])
        strata.setdefault(key, []).append(row)

    random.seed(RANDOM_SEED)
    for key in strata:
        random.shuffle(strata[key])

    print("\nStratum sizes in sampling frame:")
    for key, rows in sorted(strata.items()):
        print(f"  {key}: {len(rows)}")

    # allocate sample slots proportionally - a stratum with twice as many
    # candidates gets roughly twice as many slots, so the sample's shape
    # mirrors the frame's shape, just scaled down to SAMPLE_SIZE
    total_frame_size = len(frame)
    sample = []
    for key, rows in strata.items():
        proportion = len(rows) / total_frame_size
        target_count = round(proportion * SAMPLE_SIZE)
        sample.extend(rows[:target_count])

    # rounding across strata can leave us a few short or over target -
    # top up or trim against the full shuffled frame to hit it exactly
    random.shuffle(frame)
    if len(sample) < SAMPLE_SIZE:
        sample_ids = set(id(r) for r in sample)
        for row in frame:
            if len(sample) >= SAMPLE_SIZE:
                break
            if id(row) not in sample_ids:
                sample.append(row)
    elif len(sample) > SAMPLE_SIZE:
        sample = sample[:SAMPLE_SIZE]

    random.shuffle(sample)

    # drop the internal helper columns (prefixed with _) before writing -
    # those were only needed for stratification, not part of the real schema
    fieldnames = [k for k in messages[0].keys() if not k.startswith("_")]
    with open(SAMPLE_OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in sample:
            writer.writerow({k: row[k] for k in fieldnames})

    # manifest records exactly how this sample was built, so it can be
    # understood and defended later without re-reading the code
    manifest_lines = [
        "Annotation sample v1",
        f"Random seed: {RANDOM_SEED}",
        f"Sample size target: {SAMPLE_SIZE}",
        f"Actual sample size: {len(sample)}",
        f"Source: {MESSAGE_FILE} ({len(messages)} total messages)",
        f"Messages excluded for exceeding {MAX_PER_THREAD}-per-thread cap: {excluded_for_thread_cap}",
        f"Sampling frame size (after thread cap): {len(frame)}",
        "",
        "Stratum sizes in final sample:",
    ]
    sample_strata = {}
    for row in sample:
        key = (row["_length_bucket"], row["_ambiguous"])
        sample_strata[key] = sample_strata.get(key, 0) + 1
    for key, count in sorted(sample_strata.items()):
        manifest_lines.append(f"  {key}: {count}")

    unique_senders = len(set(row["_sender"] for row in sample))
    manifest_lines.append("")
    manifest_lines.append(f"Unique senders represented in sample: {unique_senders}")

    with open(MANIFEST_OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(manifest_lines) + "\n")

    print(f"\nWrote {len(sample)} rows to {SAMPLE_OUTPUT}")
    print(f"Wrote manifest to {MANIFEST_OUTPUT}")
    print(f"Unique senders represented: {unique_senders}")


if __name__ == "__main__":
    main()
