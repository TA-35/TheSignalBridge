from __future__ import annotations
import logging
from pathlib import Path
import pandas as pd

# Set up logging so each stage of the wrangling process is easy to track.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)

# Create a logger specifically for this wrangling script.
log = logging.getLogger("wrangle")

# Set the main staging folder used for cleaned and processed files.
STAGING = Path("data/staging")

# Cleaned Circa input created by the previous cleaning stage.
CIRCA_IN = STAGING / "circa_clean.parquet"

# Final unified MESSAGE table output.
MESSAGE_OUT = STAGING / "message_table.parquet"

# Separate file containing the Circa evaluation information.
CIRCA_EVAL_OUT = STAGING / "circa_eval.parquet"

# Define the exact structure every source must follow in the MESSAGE table.
# This keeps Circa, Enron and future datasets consistent.
MESSAGE_SCHEMA: dict[str, str] = {
    "external_ref":"string",# Stable identifier linking back to the original row
    "source_dataset_id":"int64",# Identifies which dataset the message came from
    "raw_text":"string",# Text as it entered this wrangling stage
    "cleaned_text":"string",# Cleaned version used by later processing
    "char_count":"int64",# Number of characters in cleaned_text
    "thread_id":"string",# Groups related email replies together when available
    "collected_at":"datetime64[ns, UTC]", # Time when the row entered this pipeline
}

# These fields are required and should never contain missing values.
REQUIRED_NON_NULL = [
    "external_ref", "source_dataset_id", "raw_text",
    "cleaned_text", "char_count", "collected_at",
]

# Store basic source information so each MESSAGE row can be traced back
# to the dataset it originally came from.
SOURCE_REGISTRY = {
    "circa": {"id": 1, "name": "Circa",
              "license": "CC BY 4.0 (verify)",
              "url": "https://github.com/google-research-datasets/circa"},
    "enron": {"id": 2, "name": "Enron Email Dataset",
              "license": "Non-commercial research",
              "url": "https://www.cs.cmu.edu/~enron/"},
}

# Converts an adapter's output into the exact MESSAGE schema.
def finalize(df: pd.DataFrame, source_key: str) -> pd.DataFrame:
    """Coerce any adapter's output to the exact MESSAGE schema: correct columns,
    correct order, correct dtypes. Fails if an adapter forgot a column."""

    # Check whether any required MESSAGE columns are missing.
    missing = set(MESSAGE_SCHEMA) - set(df.columns)

    # Stop the process if the adapter failed to provide a required column.
    if missing:
        raise ValueError(f"{source_key}: adapter output missing {sorted(missing)}")

    # Create a new DataFrame so the final column order matches MESSAGE_SCHEMA.
    out = pd.DataFrame(index=df.index)

    # Convert each column to the exact data type defined in the schema.
    for col, dtype in MESSAGE_SCHEMA.items():

        # collected_at needs special handling so timestamps are always stored in UTC.
        if col == "collected_at":
            out[col] = pd.to_datetime(df[col], utc=True).astype("datetime64[ns, UTC]")

        # All other columns are converted directly to their required type.
        else:
            out[col] = df[col].astype(dtype)

    # Return the final table with a clean sequential index.
    return out.reset_index(drop=True)

# Converts cleaned Circa data into the unified MESSAGE format.
def wrangle_circa() -> pd.DataFrame:
    """Adapter: cleaned Circa parquet -> MESSAGE rows (+ eval sidecar)."""
    # Get Circa's source information from the registry.
    src = SOURCE_REGISTRY["circa"]

    # Load the cleaned Circa dataset.
    df = pd.read_parquet(CIRCA_IN)

    # Record how many cleaned rows were loaded.
    log.info("circa: loaded %d cleaned rows", len(df))

    # The Circa answer is treated as the actual message being analysed.
    # Whitespace was the only text cleaning applied earlier, so raw and cleaned
    # text are currently the same for Circa.
    answer = df["answer-Y"].astype("string").str.strip()

    # Build Circa rows using the common MESSAGE schema.
    msg = pd.DataFrame({

        # Create a unique reference that can be linked back to the original Circa row.
        "external_ref":"circa-" + df["id"].astype("string"),

        # Store the Circa source identifier from SOURCE_REGISTRY.
        "source_dataset_id": src["id"],

        # Store the answer text as it enters this stage.
        "raw_text":answer,

        # Circa uses the same value for raw and cleaned text at this point.
        "cleaned_text":answer,

        # Count the number of characters in each cleaned answer.
        "char_count":answer.str.len(),

        # Circa does not contain email style conversation threads.
        "thread_id":pd.NA,

        # Record the current UTC time when the rows enter this stage.
        "collected_at":pd.Timestamp.now(tz="UTC"),
    })

    # Keep evaluation information separate from the MESSAGE table.
    # The question, context and gold label are used to evaluate the model,
    # but they are not part of the message text itself.
    STAGING.mkdir(parents=True, exist_ok=True)

    # Build the separate Circa evaluation table.
    eval_df = pd.DataFrame({

        # Use the same reference so the evaluation row can be matched to MESSAGE.
        "external_ref": "circa-" + df["id"].astype("string"),

        # Store the original question after removing surrounding spaces.
        "question":df["question-X"].astype("string").str.strip(),

        # Store the context linked to the question and answer.
        "context":df["context"].astype("string").str.strip(),

        # Store the gold standard label used as the evaluation answer.
        "gold_label":df["goldstandard1"].astype("string"),
    })

    # Save the evaluation sidecar separately from the MESSAGE table.
    eval_df.to_parquet(CIRCA_EVAL_OUT, index=False)

    # Record where the evaluation file was saved and how many rows it contains.
    log.info("circa: wrote eval sidecar -> %s (%d rows)", CIRCA_EVAL_OUT, len(eval_df))

    # Convert the Circa MESSAGE rows to the exact required schema before returning them.
    return finalize(msg, "circa")


# Store each dataset together with its input path and adapter function.
# Enron can be added here later without changing the rest of the pipeline.
ADAPTERS = {
    "circa": (CIRCA_IN, wrangle_circa),
    # "enron": (ENRON_IN, wrangle_enron),
}


# Checks that the final MESSAGE table follows all required rules before saving.
def validate(df: pd.DataFrame) -> None:
    """Assert the table is correct before it is saved. Any failure stops the run."""

    # Confirm the columns and their order exactly match MESSAGE_SCHEMA.
    assert list(df.columns) == list(MESSAGE_SCHEMA), "column set/order mismatch"

    # Check that every column has the required data type.
    for col, dtype in MESSAGE_SCHEMA.items():
        assert str(df[col].dtype) == dtype, f"{col}: dtype {df[col].dtype} != {dtype}"

    # Make sure required columns do not contain missing values.
    for col in REQUIRED_NON_NULL:
        n = int(df[col].isna().sum())
        assert n == 0, f"{col}: {n} nulls in a required column"

    # Confirm char_count matches the real length of cleaned_text.
    bad_len = int((df["char_count"] != df["cleaned_text"].str.len()).sum())
    assert bad_len == 0, f"{bad_len} rows where char_count != len(cleaned_text)"

    # external_ref should uniquely identify every MESSAGE row.
    dupes = int(df["external_ref"].duplicated().sum())
    assert dupes == 0, f"{dupes} duplicate external_ref values"

    # Build a set of all source IDs that are currently registered.
    known = {s["id"] for s in SOURCE_REGISTRY.values()}

    # Check whether the table contains any source ID that is not registered.
    unknown = set(df["source_dataset_id"].unique()) - known

    # Stop if an unknown source identifier is found.
    assert not unknown, f"unknown source_dataset_id values: {unknown}"

    # Record that every validation check passed successfully.
    log.info("validation passed: %d rows, all checks green", len(df))


# Runs all available dataset adapters and creates the unified MESSAGE table.
def main() -> None:

    # Store the MESSAGE rows returned by each available adapter.
    frames = []

    # Go through each dataset registered in ADAPTERS.
    for key, (path, adapter) in ADAPTERS.items():

        # Skip a dataset if its cleaned input file is not available yet.
        if not path.exists():
            log.warning("%s: input %s not found — skipping", key, path)
            continue

        # Run the dataset's adapter and store its MESSAGE rows.
        frames.append(adapter())

    # Stop if none of the source datasets were available.
    if not frames:
        raise SystemExit("no source inputs found in data/staging/ — run the clean stage first")

    # Combine all source specific MESSAGE rows into one unified table.
    table = pd.concat(frames, ignore_index=True)

    # Validate the complete table before saving anything.
    validate(table)

    # Create the staging folder if it does not already exist.
    MESSAGE_OUT.parent.mkdir(parents=True, exist_ok=True)

    # Save the final unified MESSAGE table as a Parquet file.
    table.to_parquet(MESSAGE_OUT, index=False)

    # Record where the final MESSAGE table was saved.
    log.info("saved -> %s", MESSAGE_OUT)

    # Build a simple mapping from source IDs back to readable source names.
    id_to_name = {v["id"]: k for k, v in SOURCE_REGISTRY.items()}

    # Print a short summary so the final wrangling output can be checked quickly.
    print("\n=== MESSAGE table summary ===")

    # Show the total number of rows and columns.
    print(f"rows: {len(table):,}    columns: {table.shape[1]}")

    # Show how many MESSAGE rows came from each source dataset.
    print("\nrows per source:")
    print(table["source_dataset_id"].map(id_to_name).value_counts().to_string())

    # Display the final data type of every column.
    print("\ndtypes:")
    print(table.dtypes.to_string())

    # Display a small sample of the final MESSAGE table.
    print("\nsample:")
    print(table.head(3).to_string())


# Run main only when this file is executed directly.
if __name__ == "__main__":
    main()