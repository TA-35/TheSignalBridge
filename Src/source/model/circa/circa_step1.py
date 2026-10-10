"""
circa_step1.py - Circa step 1 for the final build.

Mirrors enron_step1.py: staged subcommands, each saving to data/step1/circa/,
so you can stop and commit between stages. Circa differences:
  - the message is the indirect Reply; source keeps the "Q: ... / Reply: ..." wrapper
  - signals run on the Reply only (what production sees), via flag_rule
  - no 5-120 word filter (Circa replies are often 2-4 words)
Gold is picked by the shared flag rule, not Circa's own labels, so it matches
Enron and Stanford.

Run from the repo root, one stage at a time:
  python Src/source/model/circa/circa_step1.py clean
  python Src/source/model/circa/circa_step1.py pii
  python Src/source/model/circa/circa_step1.py dedupe
  python Src/source/model/circa/circa_step1.py signals
  python Src/source/model/circa/circa_step1.py split
"""

import sys
import csv
import json
import re
import random
import hashlib
from pathlib import Path

import pandas as pd
from datasketch import MinHash, MinHashLSH

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from Src.source.data_prep import flag_rule as fr

RAW = Path("data/raw/circa-data.tsv")  # Path to the original Circa dataset
WORK = Path("data/step1/circa")  # Folder to save files from each processing stage
POOL_SIZE = 10000  # Keep 10,000 records to match Enron's working pool

F_CLEAN = WORK / "1_clean.jsonl"  # File for cleaned records
F_PII = WORK / "2_pii.jsonl"  # File for records after removing personal information
F_DEDUPE = WORK / "3_dedupe.jsonl"  # File for records after removing duplicates
F_SIGNALS = WORK / "4_signals.jsonl"  # File for records with calculated signals

GOLD_OUT = Path("data/gold/circa_gold.jsonl")  # File for selected gold records
SOURCE_OUT = Path("data/source/circa_source.jsonl")  # File for selected source records
RESERVE_OUT = WORK / "gold_reserve.jsonl"  # File for extra gold records
REVIEW_OUT = WORK / "gold_review.csv"  # CSV file for manually checking gold records
COUNTS_OUT = WORK / "counts.json"  # File for saving the number of records in each group


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)  # Create the output folder if it does not exist

    with open(path, "w", encoding="utf-8") as f:  # Open the file for writing
        for r in records:  # Go through each record
            f.write(json.dumps(r, ensure_ascii=False) + "\n")  # Save each record as one JSON line


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:  # Open the JSONL file
        return [json.loads(line) for line in f]  # Read every line and convert it into a Python dictionary


def _norm(text):
    t = re.sub(r"[^\w\s]", " ", text.lower())  # Convert text to lowercase and replace punctuation with spaces
    return re.sub(r"\s+", " ", t).strip()  # Remove extra spaces and return the cleaned text


def clean():
    """Shape Circa into Q/Reply records, drop empties, exact dedupe, sample 10k."""

    df = pd.read_csv(RAW, sep="\t")  # Load the original tab-separated Circa dataset
    recs = []  # Store the cleaned records

    for _, r in df.iterrows():  # Go through each row in the dataset
        q = str(r["question-X"]).strip()  # Get the question and remove extra spaces
        a = str(r["answer-Y"]).strip()  # Get the reply and remove extra spaces

        if not a or a.lower() == "nan":
            continue  # Skip rows with empty or missing replies

        recs.append({
            "id": f"circa_{int(r['id']):05d}",  # Create a unique ID for the record
            "dataset": "circa",  # Store the dataset name
            "source": f"Q: {q}\nReply: {a}",  # Keep the question and reply together
        })

    print(f"shaped: {len(recs):,}")  # Show the number of records after formatting

    seen, kept = set(), []  # Store seen record hashes and records without duplicates

    for rec in recs:  # Check each record for exact duplicates
        h = hashlib.sha1(_norm(rec["source"]).encode("utf-8")).hexdigest()  # Create a hash from the cleaned source text

        if h in seen:
            continue  # Skip the record if the same hash already exists

        seen.add(h)  # Remember the hash to detect duplicates later
        kept.append(rec)  # Keep the record if it is not a duplicate

    print(f"after exact dedupe: {len(kept):,}")  # Show the number of records after removing duplicates

    random.seed(fr.SEED)  # Set a fixed seed so the same sample can be selected again

    if len(kept) > POOL_SIZE:
        kept = random.sample(kept, POOL_SIZE)  # Randomly select 10,000 records if there are more than needed

    print(f"working pool: {len(kept):,}")  # Show the final working pool size

    _write_jsonl(F_CLEAN, kept)  # Save the cleaned records
    print(f"wrote {F_CLEAN}")  # Show where the cleaned file was saved


def pii():
    """Presidio + one seeded Faker map, so a real value always maps to one fake."""

    from presidio_analyzer import AnalyzerEngine
    from faker import Faker

    recs = _read_jsonl(F_CLEAN)  # Load the cleaned records
    fake = Faker()  # Create a Faker object to generate fake personal details
    Faker.seed(fr.SEED)  # Set a fixed seed for generating fake values
    mapping, analyzer = {}, AnalyzerEngine()  # Store real-to-fake values and create the PII detector
    entities = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"]  # Select the types of personal information to detect

    def pseudo(real, kind):
        key = (kind, real.lower())  # Create a key using the information type and lowercase value

        if key not in mapping:  # Generate a fake value only if it has not been replaced before
            if kind == "PERSON":
                mapping[key] = fake.first_name()  # Replace a person's name with a fake first name

            elif kind == "EMAIL_ADDRESS":
                mapping[key] = fake.email()  # Replace an email address with a fake email

            else:
                mapping[key] = fake.phone_number()  # Replace a phone number with a fake number

        return mapping[key]  # Return the same fake value whenever the real value appears again

    changed = 0  # Count how many records have personal information replaced

    for rec in recs:  # Go through each cleaned record
        text = rec["source"]  # Get the question and reply text

        results = analyzer.analyze(text=text, entities=entities, language="en")  # Find personal information in the text

        for res in sorted(results, key=lambda r: r.start, reverse=True):  # Replace matches from right to left to keep positions correct
            real = text[res.start:res.end]  # Get the detected personal information
            text = text[:res.start] + pseudo(real, res.entity_type) + text[res.end:]  # Replace it with a fake value

        if text != rec["source"]:
            rec["source"] = text  # Update the record with the changed text
            changed += 1  # Increase the count of changed records

    print(f"pii: {changed:,} of {len(recs):,} changed; {len(mapping):,} unique values")  # Show how many records and values were changed

    _write_jsonl(F_PII, recs)  # Save the records after replacing personal information
    print(f"wrote {F_PII}")  # Show where the PII-processed file was saved


def dedupe():
    """Remove near duplicates (MinHash, 128 perms, Jaccard 0.85)."""

    recs = _read_jsonl(F_PII)  # Load records after PII processing
    lsh = MinHashLSH(threshold=0.85, num_perm=128)  # Set up near-duplicate checking with a similarity threshold of 0.85
    out = []  # Store records that are not near duplicates

    for i, rec in enumerate(recs):  # Go through each record with its index
        m = MinHash(num_perm=128)  # Create a MinHash for the current record

        for tok in set(_norm(rec["source"]).split()):  # Get the unique words from the cleaned source text
            m.update(tok.encode("utf-8"))  # Add each word to the MinHash

        if lsh.query(m):
            continue  # Skip the record if a similar record is already stored

        lsh.insert(str(i), m)  # Add the current record to the duplicate-checking index
        out.append(rec)  # Keep the record if no near duplicate was found

    print(f"after near dedupe: {len(out):,}  (removed {len(recs) - len(out):,})")  # Show how many records remain and were removed

    _write_jsonl(F_DEDUPE, out)  # Save the records without near duplicates
    print(f"wrote {F_DEDUPE}")  # Show where the deduplicated file was saved


def signals():
    """Attach signals from the three frozen adapters, computed on the reply only.
    Resumable: appends as it goes, so an interrupt does not lose work."""

    recs = _read_jsonl(F_DEDUPE)  # Load records after duplicate removal
    done = {}  # Store records that already have signals calculated

    if F_SIGNALS.exists():  # Check if the signals file already exists
        for r in _read_jsonl(F_SIGNALS):  # Read records that were processed earlier
            done[r["id"]] = r  # Store each processed record using its ID

        print(f"resuming: {len(done):,} already signalled")  # Show how many records are already completed

    F_SIGNALS.parent.mkdir(parents=True, exist_ok=True)  # Create the signals output folder if needed

    out = []  # Store all processed records

    with open(F_SIGNALS, "a", encoding="utf-8") as f:  # Open the signals file in append mode
        for i, rec in enumerate(recs):  # Go through each record with its index

            if rec["id"] in done:
                out.append(done[rec["id"]])  # Reuse the existing signals for completed records
                continue  # Skip recalculating signals for this record

            rec["signals"] = fr.compute_signals(fr.rewritten_text(rec["source"]))  # Extract the reply and calculate its signals

            f.write(json.dumps(rec, ensure_ascii=False) + "\n")  # Save the record with its signals
            f.flush()  # Write the latest record to the file immediately
            out.append(rec)  # Add the completed record to the output list

            if (i + 1) % 200 == 0:
                print(f"  signalled {i + 1:,}/{len(recs):,}")  # Show progress after every 200 records

    print(f"signalled: {len(out):,}  ->  {F_SIGNALS}")  # Show the total processed records and output file


def split():
    """Seed 42: 45/15 gold, 30/10 reserve, 850/150 source, by the shared flag rule."""

    recs = _read_jsonl(F_SIGNALS)  # Load all records with their calculated signals

    random.seed(fr.SEED)  # Set a fixed seed to make the split reproducible
    random.shuffle(recs)  # Randomly shuffle the records before splitting

    flagged = [r for r in recs if fr.is_flagged(r)]  # Select records marked as unclear by the shared flag rule
    clear = [r for r in recs if not fr.is_flagged(r)]  # Select records that are not flagged

    print(f"flagged: {len(flagged):,}   clear: {len(clear):,}")  # Show how many flagged and clear records are available

    need_f = fr.N_GOLD_FLAGGED + fr.N_RES_FLAGGED + fr.N_SRC_FLAGGED  # Calculate the total flagged records needed
    need_c = fr.N_GOLD_CLEAR + fr.N_RES_CLEAR + fr.N_SRC_CLEAR  # Calculate the total clear records needed

    if len(flagged) < need_f or len(clear) < need_c:  # Check whether enough records are available in both groups
        print(f"WARNING: need {need_f} flagged / {need_c} clear; "
              f"have {len(flagged)} / {len(clear)}. Taking all available of the short class.")  # Warn if either group has fewer records than needed

    gf = flagged[:fr.N_GOLD_FLAGGED]  # Select flagged records for the gold set

    rf = flagged[fr.N_GOLD_FLAGGED:fr.N_GOLD_FLAGGED + fr.N_RES_FLAGGED]  # Select the next flagged records for the reserve set

    sf = flagged[fr.N_GOLD_FLAGGED + fr.N_RES_FLAGGED:
                 fr.N_GOLD_FLAGGED + fr.N_RES_FLAGGED + fr.N_SRC_FLAGGED]  # Select the remaining required flagged records for the source set

    gc = clear[:fr.N_GOLD_CLEAR]  # Select clear records for the gold set

    rc = clear[fr.N_GOLD_CLEAR:fr.N_GOLD_CLEAR + fr.N_RES_CLEAR]  # Select the next clear records for the reserve set

    sc = clear[fr.N_GOLD_CLEAR + fr.N_RES_CLEAR:
               fr.N_GOLD_CLEAR + fr.N_RES_CLEAR + fr.N_SRC_CLEAR]  # Select the remaining required clear records for the source set

    def shape(r):
        return {
            "id": r["id"],  # Keep the record ID
            "dataset": r["dataset"],  # Keep the dataset name
            "source": r["source"],  # Keep the original question and reply
            "signals": r["signals"]  # Keep the calculated signals
        }

    gold = [shape(r) for r in gf + gc]  # Combine flagged and clear records for the gold set
    reserve = [shape(r) for r in rf + rc]  # Combine flagged and clear records for the reserve set
    source = [shape(r) for r in sf + sc]  # Combine flagged and clear records for the source set

    _write_jsonl(GOLD_OUT, gold)  # Save the gold records
    _write_jsonl(SOURCE_OUT, source)  # Save the source records
    _write_jsonl(RESERVE_OUT, reserve)  # Save the reserve records

    REVIEW_OUT.parent.mkdir(parents=True, exist_ok=True)  # Create the folder for the review CSV

    with open(REVIEW_OUT, "w", encoding="utf-8", newline="") as f:  # Open the review CSV for writing
        w = csv.writer(f)  # Create a CSV writer

        w.writerow(["id", "flagged", "reasons", "source"])  # Write the column names

        for r in gf + gc:  # Go through all selected gold records
            w.writerow([
                r["id"],  # Write the record ID
                bool(fr.flag_reasons(r)),  # Show whether any flag reason exists
                "; ".join(fr.flag_reasons(r)),  # Combine all flag reasons into one text value
                r["source"]  # Include the question and reply for manual review
            ])

    counts = {
        "dataset": "circa",  # Store the dataset name
        "working_pool": len(recs),  # Count all records available after signal processing
        "flagged": len(flagged),  # Count all flagged records
        "clear": len(clear),  # Count all clear records
        "gold": {"flagged": len(gf), "clear": len(gc)},  # Count flagged and clear records in the gold set
        "reserve": {"flagged": len(rf), "clear": len(rc)},  # Count flagged and clear records in the reserve set
        "source": {"flagged": len(sf), "clear": len(sc)},  # Count flagged and clear records in the source set
    }

    COUNTS_OUT.parent.mkdir(parents=True, exist_ok=True)  # Create the folder for the counts file

    with open(COUNTS_OUT, "w", encoding="utf-8") as f:  # Open the counts JSON file
        json.dump(counts, f, indent=2)  # Save the counts in a readable JSON format

    print(f"\ngold:    {len(gold)}  -> {GOLD_OUT}")  # Show the gold set size and file location
    print(f"source:  {len(source)}  -> {SOURCE_OUT}")  # Show the source set size and file location
    print(f"reserve: {len(reserve)}  -> {RESERVE_OUT}")  # Show the reserve set size and file location
    print(f"counts   -> {COUNTS_OUT}")  # Show where the counts file was saved
    print(json.dumps(counts, indent=2))  # Display the final record counts

if __name__ == "__main__":  # Run this section only when the script is executed directly
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""  # Get the stage name from the command line

    {"clean": clean, "pii": pii, "dedupe": dedupe,
     "signals": signals, "split": split}.get(cmd, lambda: print(
        "usage: circa_step1.py [clean|pii|dedupe|signals|split]"))()  # Run the selected stage or show the usage instructions