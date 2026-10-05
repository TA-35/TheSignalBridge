import pandas as pd
from pathlib import Path
from presidio_analyzer import AnalyzerEngine
from faker import Faker
import re
import hashlib
from datasketch import MinHash, MinHashLSH
import json
import random

# Path to the raw Circa dataset
RAW = Path("data/raw/circa-data.tsv")

def load_circa():
    # Check that the dataset exists before trying to load it
    if not RAW.exists():
        raise FileNotFoundError(
            f"Cannot find {RAW}. Download circa-data.tsv from the "
            f"google-research-datasets/circa repo into data/raw/ first."
        )

    # Load the TSV file into a pandas DataFrame
    df = pd.read_csv(RAW, sep="\t")

    # Show the dataset size after loading
    print(f"loaded circa: {len(df):,} rows, {df.shape[1]} columns")

    # Display the available columns to check the dataset structure
    print("\ncolumns:", list(df.columns))

    # Print the first row as a quick check of the loaded data
    print("\nfirst row:")
    for k, v in df.iloc[0].items():
        print(f"  {k!r}: {v!r}")

    # Return the DataFrame for the next processing steps
    return df

def shape_rows(df):
    # Convert each Circa row into the format needed by our pipeline
    records = []

    # Go through each row in the dataset
    for _, r in df.iterrows():
        # Get and clean the question, answer and gold label
        question = str(r["question-X"]).strip()
        answer = str(r["answer-Y"]).strip()
        gold = str(r["goldstandard1"]).strip()

        # Yes or No is clear, while every other label is treated as unclear
        is_unclear = gold not in ("Yes", "No")

        # Create one structured record for each Circa response
        records.append({
            "id": f"circa_{int(r['id']):05d}",
            "dataset": "circa",
            "source": f"Q: {question}\nReply: {answer}",
            "is_unclear": is_unclear,  # Used later when creating the gold split
        })

    # Show how many records were created
    print(f"shaped {len(records):,} records")

    # Count how many responses are unclear or indirect
    unclear = sum(x["is_unclear"] for x in records)

    # Print the clear and unclear response counts
    print(f"  unclear (indirect): {unclear:,}")
    print(f"  clear (yes/no):     {len(records) - unclear:,}")

    # Show one record to quickly check the final structure
    print("\nexample record:")
    for k, v in records[0].items():
        print(f"  {k!r}: {v!r}")

    # Return all shaped records for the next processing step
    return records

# Create one Faker instance and keep the generated fake values consistent
_fake = Faker()

# Use a fixed seed so the generated fake data stays reproducible
Faker.seed(42)

# Store the mapping between real and fake values
_mapping = {}

# Create the analyzer used to detect personal information
_analyzer = AnalyzerEngine()

def _pseudo(real, kind):
    # Use the type and real value as a unique mapping key
    key = (kind, real.lower())

    # Generate a fake value only if this value has not been seen before
    if key not in _mapping:
        if kind == "PERSON":
            _mapping[key] = _fake.first_name()
        elif kind == "EMAIL_ADDRESS":
            _mapping[key] = _fake.email()
        else:
            _mapping[key] = _fake.phone_number()

    # Return the same fake value whenever this real value appears again
    return _mapping[key]

def scrub_pii(records):
    # Define the types of personal information we want to detect
    entities = ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"]

    # Keep track of how many messages are changed
    n_changed = 0

    # Go through each message in the records
    for rec in records:
        text = rec["source"]

        # Find any personal information in the message
        results = _analyzer.analyze(text=text, entities=entities, language="en")

        # Skip the message if no personal information is found
        if not results:
            continue

        # Replace from right to left so the text positions remain correct
        for res in sorted(results, key=lambda r: r.start, reverse=True):
            real = text[res.start:res.end]
            text = text[:res.start] + _pseudo(real, res.entity_type) + text[res.end:]

        # Save the cleaned message if any replacement was made
        if text != rec["source"]:
            rec["source"] = text
            n_changed += 1

    # Show how many messages contained personal information
    print(f"PII scrub: {n_changed:,} of {len(records):,} messages had a replacement")

    # Show how many unique real values were replaced
    print(f"unique real values pseudonymised: {len(_mapping):,}")

    # Return the records with personal information replaced
    return records

def _norm(text):
    # Convert text to lowercase for consistent comparison
    t = text.lower()
    # Remove punctuation from the text
    t = re.sub(r"[^\w\s]", " ", t)
    # Remove extra spaces and clean the final text
    t = re.sub(r"\s+", " ", t).strip()
    # Return the normalised text
    return t

def deduplicate(records):
    # Store unique records after the exact duplicate check
    seen, kept = set(), []

    # Go through each record and check for exact duplicates
    for rec in records:
        # Create a hash from the normalised message
        h = hashlib.sha1(_norm(rec["source"]).encode("utf-8")).hexdigest()

        # Skip the record if the same message was already seen
        if h in seen:
            continue

        # Keep the hash and its unique record
        seen.add(h)
        kept.append(rec)

    # Store the number of records remaining after exact deduplication
    after_exact = len(kept)

    # Show how many exact duplicates were removed
    print(f"after exact dedup:   {after_exact:,}  (removed {len(records) - after_exact:,})")

    # Set up MinHash LSH to find messages that are very similar
    lsh = MinHashLSH(threshold=0.85, num_perm=128)
    final = []

    # Go through the remaining records and check for near duplicates
    for i, rec in enumerate(kept):
        # Split the normalised message into unique words
        tokens = set(_norm(rec["source"]).split())

        # Create a MinHash representation of the message
        m = MinHash(num_perm=128)

        # Add each word to the MinHash
        for tok in tokens:
            m.update(tok.encode("utf-8"))

        # Skip the message if a similar one has already been kept
        if lsh.query(m):
            continue

        # Add the unique message to the LSH index
        lsh.insert(str(i), m)

        # Keep the record in the final dataset
        final.append(rec)

    # Show how many near duplicates were removed
    print(f"after near dedup:    {len(final):,}  (removed {after_exact - len(final):,})")

    # Return the final deduplicated records
    return final

# Path where the final gold set will be saved
GOLD_OUT = Path("data/gold/circa_gold.jsonl")

def make_gold_and_pool(records):
    # Use a fixed seed so the same gold set is selected every time
    random.seed(42)

    # Separate the records into unclear and clear responses
    unclear = [r for r in records if r["is_unclear"]]
    clear = [r for r in records if not r["is_unclear"]]

    # Show how many records are available in each group
    print(f"pool available -> unclear: {len(unclear):,}, clear: {len(clear):,}")

    # Randomly select 45 unclear and 15 clear messages for the gold set
    gold_unclear = random.sample(unclear, 45)
    gold_clear = random.sample(clear, 15)

    # Combine both groups into the final gold set
    gold = gold_unclear + gold_clear

    # Store gold IDs so they can be removed from the remaining pool
    gold_ids = {r["id"] for r in gold}

    # Show the final gold set distribution
    print(f"gold drawn: {len(gold)} ({len(gold_unclear)} unclear + {len(gold_clear)} clear)")

    # Create MinHashes for gold messages to check for similar records
    gold_minhashes = []

    # Build a MinHash for every message in the gold set
    for r in gold:
        tokens = set(_norm(r["source"]).split())
        m = MinHash(num_perm=128)

        # Add each unique word to the MinHash
        for tok in tokens:
            m.update(tok.encode("utf-8"))

        gold_minhashes.append(m)

    def is_near_gold(rec):
        # Create a MinHash for the record being checked
        tokens = set(_norm(rec["source"]).split())
        m = MinHash(num_perm=128)

        # Add each unique word to the MinHash
        for tok in tokens:
            m.update(tok.encode("utf-8"))

        # Check if the record is too similar to any gold message
        for gm in gold_minhashes:
            if m.jaccard(gm) >= 0.85:
                return True

        return False

    # Store records that are safe to keep in the remaining pool
    pool = []
    removed_near = 0

    # Remove gold records and anything too similar to them
    for rec in records:
        if rec["id"] in gold_ids:
            continue

        if is_near_gold(rec):
            removed_near += 1
            continue

        pool.append(rec)

    # Show how many records were removed and how many remain
    print(f"removed from pool: 60 gold + {removed_near} near-duplicates of gold")
    print(f"pool remaining: {len(pool):,}")

    # Create the gold output folder if it does not already exist
    GOLD_OUT.parent.mkdir(parents=True, exist_ok=True)

    # Save the gold records without the helper field
    with open(GOLD_OUT, "w", encoding="utf-8") as f:
        for r in gold:
            out = {
                "id": r["id"],
                "dataset": r["dataset"],
                "source": r["source"]
            }
            f.write(json.dumps(out) + "\n")

    # Confirm where the gold set was saved
    print(f"wrote {len(gold)} gold messages -> {GOLD_OUT}")

    # Return both the gold set and remaining pool
    return gold, pool

# Run the loading and shaping steps when this file is executed directly
if __name__ == "__main__":
    df = load_circa()
    records = shape_rows(df)
    records = scrub_pii(records)
    records = deduplicate(records)
    gold, pool = make_gold_and_pool(records)