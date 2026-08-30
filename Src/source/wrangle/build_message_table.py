"""
build_message_table.py

Takes the cleaned Enron data and reshapes it into the MESSAGE and
EMAIL_META tables from our ERD, instead of the flat parsed/cleaned CSV
shape it's been in so far.

Why this step exists: every source we bring in (Enron, Circa, and
whatever else) needs to end up looking the same way once it reaches the
database - one row per message in MESSAGE, with a consistent set of
columns, regardless of which dataset it came from. Enron has extra
fields (sender, recipients, subject, date) that a lot of other sources
won't have, so those live in a separate EMAIL_META table instead of
MESSAGE itself - that way MESSAGE stays generic and any source can slot
into it, and only the sources that actually have email-style metadata
need a matching EMAIL_META row.

This script only handles Enron for now. Once Circa is cleaned, it gets
its own equivalent script that produces rows in the same MESSAGE shape
(with EMAIL_META left empty, since Circa isn't email).

Input:  data/staging/enron_cleaned.csv
Output: data/staging/message_enron.csv       (rows for the MESSAGE table)
        data/staging/email_meta_enron.csv    (rows for the EMAIL_META table)
"""

import csv
import uuid
from pathlib import Path

csv.field_size_limit(10_000_000)

STAGING_DIR = Path("data/staging")
INPUT_FILE = STAGING_DIR / "enron_cleaned.csv"
MESSAGE_OUTPUT = STAGING_DIR / "message_enron.csv"
EMAIL_META_OUTPUT = STAGING_DIR / "email_meta_enron.csv"

MESSAGE_FIELDNAMES = [
    "message_id",       # our own generated ID for this table - not the same as the email's own Message-ID header
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


def build_thread_id(row: dict) -> str:
    """
    Groups emails into threads using In-Reply-To first, since that's the
    most direct signal - it points straight at the message being replied
    to. If that's missing, we fall back to subject + sender, which isn't
    as precise (two unrelated emails with the same subject line would get
    grouped together) but is a reasonable approximation when the more
    reliable header isn't available.
    """
    if row["in_reply_to"].strip():
        return row["in_reply_to"].strip()

    # crude fallback: same subject line often means same conversation
    subject = row["subject"].strip().lower()
    subject = subject.replace("re:", "").replace("fw:", "").strip()
    if subject:
        return f"subject::{subject}"

    # no usable signal at all - treat as its own standalone thread
    return f"standalone::{row['message_id']}"


def main():
    if not INPUT_FILE.exists():
        print(f"ERROR: {INPUT_FILE} not found. Run clean_enron.py first.")
        return

    with open(INPUT_FILE, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    message_rows = []
    email_meta_rows = []

    for row in rows:
        # We generate our own message_id here rather than reusing the
        # email's Message-ID header directly - the header is specific to
        # email as a format, but MESSAGE needs to work for any source
        # (Circa questions don't have a Message-ID at all), so every
        # source generates its own uuid instead and MESSAGE stays generic.
        our_message_id = str(uuid.uuid4())

        message_rows.append({
            "message_id": our_message_id,
            "source_dataset_id": "enron",
            "raw_text": row["raw_body"],
            "cleaned_text": row["body"],
            "char_count": len(row["body"]),
            "external_ref": row["external_ref"],
            "thread_id": build_thread_id(row),
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

    print(f"Wrote {len(message_rows)} rows to {MESSAGE_OUTPUT}")
    print(f"Wrote {len(email_meta_rows)} rows to {EMAIL_META_OUTPUT}")


if __name__ == "__main__":
    main()
