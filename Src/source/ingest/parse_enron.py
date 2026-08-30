"""
parse_enron.py

Phase 1 (Ingest & parse) - Enron dataset.

Walks the Enron maildir tree (data/raw/enron/maildir/<person>/<folder>/<file>),
parses each file as a standard RFC-822 email, and writes one row per email
into a staging CSV with structured header fields separated from the body.

This is a faithful parse only - no cleaning, deduplication, or filtering
happens here (that's Phase 2). The goal is just to get every email into a
consistent structured shape in data/staging/.

Usage:
    python Src/source/ingest/parse_enron.py

Output:
    data/staging/enron_parsed.csv
"""

import csv
import email
from email import policy
from pathlib import Path
import sys

# Paths are relative to the repo root - script expects to be run from there.
RAW_DIR = Path("data/raw/enron/maildir")
STAGING_DIR = Path("data/staging")
OUTPUT_FILE = STAGING_DIR / "enron_parsed.csv"

FIELDNAMES = [
    "source_dataset",
    "person",          # mailbox owner, e.g. "campbell-l"
    "folder",          # subfolder path under the person, e.g. "sent" or "pcb_modeling_study"
    "file_id",         # original filename, e.g. "1", "61"
    "message_id",
    "from_",
    "to",
    "cc",
    "subject",
    "date",
    "in_reply_to",
    "references",
    "body",
    "raw_char_count",
    "external_ref",    # path relative to maildir/, doubles as a stable reference
]


def parse_one_email(filepath: Path):
    """Parse a single Enron email file into a dict of structured fields."""
    try:
        raw_bytes = filepath.read_bytes()
    except Exception as e:
        return None, f"read error: {e}"

    try:
        # Enron files are not strictly UTF-8; decode leniently and let the
        # email parser handle header decoding. Errors="replace" avoids hard
        # crashes on the messier files - Phase 2 will handle encoding cleanup.
        raw_text = raw_bytes.decode("utf-8", errors="replace")
        msg = email.message_from_string(raw_text, policy=policy.default)
    except Exception as e:
        return None, f"parse error: {e}"

    # Body extraction - Enron emails are plain text, but some are multipart.
    try:
        if msg.is_multipart():
            body_parts = []
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body_parts.append(part.get_content())
            body = "\n".join(body_parts)
        else:
            body = msg.get_content()
    except Exception:
        # Fall back to the raw payload if get_content() chokes on encoding
        try:
            body = msg.get_payload(decode=True)
            body = body.decode("utf-8", errors="replace") if body else ""
        except Exception:
            body = ""

    row = {
        "message_id": msg.get("Message-ID", ""),
        "from_": msg.get("From", ""),
        "to": msg.get("To", ""),
        "cc": msg.get("Cc", ""),
        "subject": msg.get("Subject", ""),
        "date": msg.get("Date", ""),
        "in_reply_to": msg.get("In-Reply-To", ""),
        "references": msg.get("References", ""),
        "body": body.strip() if body else "",
        "raw_char_count": len(raw_text),
    }
    return row, None


def main():
    if not RAW_DIR.exists():
        print(f"ERROR: {RAW_DIR} does not exist. Did you extract the Enron "
              f"tarball into data/raw/enron/ ?")
        sys.exit(1)

    STAGING_DIR.mkdir(parents=True, exist_ok=True)

    all_files = [p for p in RAW_DIR.rglob("*") if p.is_file()]
    total = len(all_files)
    print(f"Found {total} files under {RAW_DIR}")

    written = 0
    errors = 0
    error_log = []

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=FIELDNAMES)
        writer.writeheader()

        for i, filepath in enumerate(all_files, 1):
            # e.g. maildir/campbell-l/sent/1        -> person=campbell-l, folder=sent,   file_id=1
            #      maildir/campbell-l/1              -> person=campbell-l, folder="",     file_id=1
            #      maildir/campbell-l/a/b/1           -> person=campbell-l, folder=a/b,    file_id=1
            # The previous version of this line had a bug: when a file sat
            # directly under the person folder with no subfolder (the second
            # case above), it accidentally copied the filename into `folder`
            # too. Fixed by only joining the *middle* parts (excluding both
            # the person and the filename) - if there are no middle parts,
            # folder is correctly just an empty string.
            rel = filepath.relative_to(RAW_DIR)
            parts = rel.parts
            person = parts[0] if len(parts) >= 1 else ""
            folder = "/".join(parts[1:-1])  # empty string if nothing between person and file
            file_id = parts[-1]

            row, err = parse_one_email(filepath)
            if err:
                errors += 1
                error_log.append((str(rel), err))
                continue

            row["source_dataset"] = "enron"
            row["person"] = person
            row["folder"] = folder
            row["file_id"] = file_id
            row["external_ref"] = str(rel)

            writer.writerow(row)
            written += 1

            if i % 25000 == 0:
                print(f"  processed {i}/{total} files "
                      f"({written} written, {errors} errors)")

    print(f"\nDone. {written} emails written to {OUTPUT_FILE}")
    print(f"{errors} files failed to parse.")

    if error_log:
        error_log_path = STAGING_DIR / "enron_parse_errors.csv"
        with open(error_log_path, "w", newline="", encoding="utf-8") as ef:
            ew = csv.writer(ef)
            ew.writerow(["file", "error"])
            ew.writerows(error_log)
        print(f"Error details written to {error_log_path}")


if __name__ == "__main__":
    main()
