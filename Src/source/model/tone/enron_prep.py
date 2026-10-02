# enron_prep.py
# cleaning + sampling for the tone model. run this before labelling.
# input: data/staging/enron_parsed.csv
# output: data/processed/enron_tone_sample_3k.csv + a report txt

import csv, email, hashlib, re, random
from pathlib import Path
import spacy

csv.field_size_limit(10_000_000)

INPUT_FILE = Path("data/staging/enron_parsed.csv")
OUTPUT_FILE = Path("data/processed/enron_tone_sample_3k.csv")
REPORT_FILE = Path("data/processed/enron_prep_report.txt")

SAMPLE_SIZE = 3000
MIN_WORDS, MAX_WORDS = 5, 200

nlp = spacy.load("en_core_web_sm", disable=["parser", "lemmatizer", "tagger", "attribute_ruler"])


def parse_message(raw):
    msg = email.message_from_string(raw)
    if msg.is_multipart():
        body = ""
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                body = payload.decode("utf-8", errors="ignore") if payload else ""
                break
    else:
        payload = msg.get_payload(decode=True)
        body = payload.decode("utf-8", errors="ignore") if payload else msg.get_payload()

    return {
        "from_": msg.get("From", ""),
        "to": msg.get("To", ""),
        "subject": msg.get("Subject", ""),
        "date": msg.get("Date", ""),
        "message_id": msg.get("Message-ID", ""),
        "body": body or "",
    }


def normalize_row(r):
    if "message" in r and r["message"]:
        return parse_message(r["message"])

    body = r.get("body") or r.get("cleaned_text") or r.get("cleaned_body") or r.get("raw_text") or ""

    return {
        "from_": r.get("from_") or r.get("from") or r.get("person") or "",
        "to": r.get("to") or "",
        "subject": r.get("subject") or "",
        "date": r.get("date") or "",
        "message_id": r.get("message_id") or r.get("file_id") or "",
        "body": body,
    }


def strip_quoted_history(body):
    if not body:
        return body
    cuts = []
    m = re.search(r"-----Original Message-----", body, re.IGNORECASE)
    if m: cuts.append(m.start())
    m = re.search(r"\nOn .{0,80} wrote:\s*\n", body)
    if m: cuts.append(m.start())
    if cuts:
        body = body[:min(cuts)]
    lines = [l for l in body.split("\n") if not l.strip().startswith(">")]
    return "\n".join(lines).strip()


SIG_PATTERNS = [
    r"\n--\s*\n.*",
    r"\n\+?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\n.*",
]

def strip_signature(body):
    if not body:
        return body
    for p in SIG_PATTERNS:
        m = re.search(p, body, re.IGNORECASE | re.DOTALL)
        if m:
            body = body[:m.start()]
    return body.strip()


def norm_for_dedup(text):
    return re.sub(r"\s+", " ", text.lower()).strip()


def dedupe_rows(rows):
    seen, kept = set(), []
    for r in rows:
        h = hashlib.md5(norm_for_dedup(r["body"]).encode("utf-8", "ignore")).hexdigest()
        if h in seen:
            continue
        seen.add(h)
        kept.append(r)
    return kept, len(rows) - len(kept)


def word_count(t):
    return len(t.split())


EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_RE = re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b")


def scrub_pii_batch(bodies):
    pre_scrubbed = []
    for body in bodies:
        b = EMAIL_RE.sub("[EMAIL_REDACTED]", body)
        b = PHONE_RE.sub("[PHONE_REDACTED]", b)
        pre_scrubbed.append(b)

    results = []
    total = len(pre_scrubbed)
    for i, doc in enumerate(nlp.pipe(pre_scrubbed, batch_size=100)):
        out = doc.text
        for ent in sorted(doc.ents, key=lambda e: -len(e.text)):
            if ent.label_ == "PERSON":
                out = out.replace(ent.text, "[PERSON_REDACTED]")
            elif ent.label_ == "ORG":
                out = out.replace(ent.text, "[ORG_REDACTED]")
        results.append(out)

        if (i + 1) % 250 == 0 or (i + 1) == total:
            print(f"  pii scrub: {i + 1}/{total}")

    return results


def main():
    if not INPUT_FILE.exists():
        print(f"cant find {INPUT_FILE}")
        return

    report = []
    with open(INPUT_FILE, newline="", encoding="utf-8") as f:
        raw_rows = list(csv.DictReader(f))
    report.append(f"starting rows: {len(raw_rows)}")

    rows = [normalize_row(r) for r in raw_rows]
    report.append(f"after parsing: {len(rows)}")

    for r in rows:
        r["body"] = strip_quoted_history(r["body"])
        r["body"] = strip_signature(r["body"])
    report.append(f"after stripping quotes/sigs: {len(rows)}")

    rows, dropped = dedupe_rows(rows)
    report.append(f"after dedup: {len(rows)} (removed {dropped})")

    before = len(rows)
    rows = [r for r in rows if MIN_WORDS <= word_count(r["body"]) <= MAX_WORDS]
    report.append(f"after length filter: {len(rows)} (removed {before - len(rows)})")

    random.seed(42)
    sample = random.sample(rows, min(SAMPLE_SIZE, len(rows)))
    report.append(f"sampled: {len(sample)}")

    print(f"scrubbing pii on {len(sample)} rows (batched, should be quicker)...")
    bodies = scrub_pii_batch([r["body"] for r in sample])
    for r, b in zip(sample, bodies):
        r["body"] = b
    report.append(f"pii scrubbed on {len(sample)} rows")

    Path("data/processed").mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["from_", "to", "subject", "date", "message_id", "body"])
        w.writeheader()
        w.writerows(sample)

    with open(REPORT_FILE, "w") as f:
        f.write("\n".join(report) + "\n")

    print("\n".join(report))
    print(f"\nwritten to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()