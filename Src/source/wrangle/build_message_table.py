"""
build_message_table.py

Takes the cleaned Enron data and reshapes it into the MESSAGE and
EMAIL_META tables from our ERD, so Enron ends up looking the same way any
other source (like Circa) will once it's wrangled too - one row per
message in MESSAGE, with Enron-specific fields like sender/subject/date
living separately in EMAIL_META.

A note on thread reconstruction, since this took two attempts to get
right: we originally planned to link replies together using the
In-Reply-To and References email headers, which is the standard, most
reliable way to reconstruct threads. We checked directly against this
dataset and both headers are 0% populated - completely empty on all
496,679 rows, not just rare. So that approach is a dead end here, and
this script doesn't try to use it.

Instead, threads are grouped using the only real signal we actually
have: same normalised subject line + same sender, and only within a
7-day window of each other. The time window matters - without it, two
completely unrelated emails that happen to share a generic subject like
"Meeting" would get merged into one "thread" just because the words
matched, which would be wrong. This is a real limitation compared to
proper header-based threading (it can't catch a reply from someone who
didn't share the exact normalised subject, for example), and it's
recorded as a known gap in SOURCE_DATASET.md rather than something this
script quietly papers over.

Input:  data/staging/enron_cleaned.csv
Output: data/staging/message_enron.csv       (rows for the MESSAGE table)
        data/staging/email_meta_enron.csv    (rows for the EMAIL_META table)
"""

import csv
import re
import uuid
from pathlib import Path

csv.field_size_limit(10_000_000)

STAGING_DIR = Path("data/staging")
INPUT_FILE = STAGING_DIR / "enron_cleaned.csv"
MESSAGE_OUTPUT = STAGING_DIR / "message_enron.csv"
EMAIL_META_OUTPUT = STAGING_DIR / "email_meta_enron.csv"

MESSAGE_FIELDNAMES = [
    "message_id",        # our own generated id for this table - not the same as Enron's Message-ID header
    "source_dataset_id",
    "raw_text",
    "cleaned_text",
    "char_count",
    "external_ref",       # path back to the original file, e.g. maildir/campbell-l/sent/12
    "thread_id",
]

EMAIL_META_FIELDNAMES = [
    "message_id",   # links back to the MESSAGE row this metadata belongs to
    "sender",
    "recipients",
    "cc",
    "subject",
    "sent_at",
]


def parse_email_date(date_str: str):
    """
    Enron dates are in RFC-822 format, e.g. 'Mon, 24 Sep 2001 08:17:17 -0700'.
    We need a real datetime object to compare timestamps for thread
    grouping below. A handful of dates in this dataset are malformed, so
    if parsing fails we return None and treat that row as having no
    usable timestamp, rather than crashing the whole script.
    """
    if not date_str:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except Exception:
        return None


def normalize_subject(subject: str) -> str:
    """
    Strips "Re:" / "Fw:" / "Fwd:" prefixes so "Budget", "Re: Budget", and
    "Re: Fwd: Budget" all normalise down to the same string. Without
    this, a reply chain would look like an unrelated new topic every time
    someone hit reply or forward.
    """
    subject = subject.strip().lower()
    subject = re.sub(r"^(re|fw|fwd)\s*:\s*", "", subject)
    subject = re.sub(r"^(re|fw|fwd)\s*:\s*", "", subject)  # run twice - catches "Re: Fw: X"
    return subject.strip()


def build_thread_ids(rows):
    """
    Groups rows into threads by (normalised subject, sender), then within
    each group, splits it further by time - if two emails in the same
    subject+sender group are more than 7 days apart, they start a new
    thread rather than being lumped into one. Emails with no subject at
    all, or no parseable date, can't be safely grouped, so each one just
    becomes its own standalone thread instead of guessing.

    Returns a dict mapping each row's position in the list (its index) to
    a thread_id string. We use the row's index as the key rather than its
    Message-ID, since it's simpler and every row has a valid index
    regardless of what's in its other fields.
    """
    groups = {}  # (subject, sender) -> list of (index, date)

    for i, row in enumerate(rows):
        subject = normalize_subject(row["subject"])
        sender = row["from_"].strip().lower()
        date = parse_email_date(row["date"])
        groups.setdefault((subject, sender), []).append((i, date))

    thread_ids = {}

    for (subject, sender), entries in groups.items():
        if not subject:
            # nothing to group by - every row in this bucket stands alone
            for i, _ in entries:
                thread_ids[i] = f"standalone::{uuid.uuid4()}"
            continue

        with_dates = [(i, d) for i, d in entries if d is not None]
        without_dates = [i for i, d in entries if d is None]

        # sort by date so we can check the gap between consecutive emails
        with_dates.sort(key=lambda pair: pair[1])

        current_thread_id = None
        last_date = None

        for i, date in with_dates:
            if last_date is None or (date - last_date).days > 7:
                # first email in this group, or too big a gap since the
                # last one - starts a fresh thread
                current_thread_id = f"thread::{subject}::{sender}::{date.isoformat()}"
            thread_ids[i] = current_thread_id
            last_date = date

        # can't time-check these, so each gets its own thread rather than a guess
        for i in without_dates:
            thread_ids[i] = f"standalone::{uuid.uuid4()}"

    return thread_ids


def main():
    if not INPUT_FILE.exists():
        print(f"ERROR: {INPUT_FILE} not found. Run clean_enron.py first.")
        return

    with open(INPUT_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} cleaned rows.")
    print("Grouping into threads by subject + sender + time proximity...")
    thread_id_map = build_thread_ids(rows)

    message_rows = []
    email_meta_rows = []

    for i, row in enumerate(rows):
        our_message_id = str(uuid.uuid4())

        message_rows.append({
            "message_id": our_message_id,
            "source_dataset_id": "enron",
            "raw_text": row["raw_body"],
            "cleaned_text": row["body"],
            "char_count": len(row["body"]),
            "external_ref": row["external_ref"],
            "thread_id": thread_id_map[i],
        })

        email_meta_rows.append({
            "message_id": our_message_id,
            "sender": row["from_"],
            "recipients": row["to"],
            "cc": row["cc"],
            "subject": row["subject"],
            "sent_at": row["date"],
        })

    with open(MESSAGE_OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MESSAGE_FIELDNAMES)
        writer.writeheader()
        writer.writerows(message_rows)

    with open(EMAIL_META_OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=EMAIL_META_FIELDNAMES)
        writer.writeheader()
        writer.writerows(email_meta_rows)

    unique_threads = len(set(r["thread_id"] for r in message_rows))
    standalone_count = sum(1 for r in message_rows if r["thread_id"].startswith("standalone::"))
    grouped_count = len(message_rows) - standalone_count

    print(f"\nWrote {len(message_rows)} rows to {MESSAGE_OUTPUT}")
    print(f"Wrote {len(email_meta_rows)} rows to {EMAIL_META_OUTPUT}")
    print(f"Grouped into {unique_threads} distinct threads")
    print(f"  - {grouped_count} rows grouped by subject+sender+time")
    print(f"  - {standalone_count} rows had no usable subject/date and stand alone")


if __name__ == "__main__":
    main()
