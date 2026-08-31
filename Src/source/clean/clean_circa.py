import pandas as pd
from pathlib import Path

# Set the location of the raw input file and the cleaned output file.
RAW = Path("data/raw/circa-data.tsv")
OUT = Path("data/staging/circa_clean.parquet")

# Column containing the final gold standard label for each response.
LABEL_COL = "goldstandard1"

# Decide how duplicate question and answer pairs should be handled.
# "qa" removes repeated question and answer pairs even if their context differs.
# "qac" only removes them when the question, answer and context are all the same.
# This allows the team to decide whether different context should make a row unique.
DEDUPE_RULE = "qa"   # change to "qac" if context makes them distinct


# Displays a small sample of duplicate question and answer groups before removing them.
# This helps check the duplicates manually before deciding which rule to use.
def inspect_duplicates(df: pd.DataFrame, n_groups: int = 8) -> None:
    """Read-only: print a few duplicate Q-A groups so the dedupe rule is an
    informed choice, not a blind delete."""

    # Find every row where the same question and answer combination appears more than once.
    mask = df.duplicated(subset=["question-X", "answer-Y"], keep=False)

    # Keep only duplicate rows and sort them so matching pairs appear together.
    dupes = df[mask].sort_values(["question-X", "answer-Y"])

    # Show how many rows belong to duplicate groups.
    print(f"\n{mask.sum()} rows belong to a duplicate (question, answer) group. "
          f"Showing first {n_groups}:\n")

    shown = 0

    # Go through each duplicate question and answer group separately.
    for (q, a), group in dupes.groupby(["question-X", "answer-Y"]):
        print("-" * 68)
        print(f"Q: {q}")
        print(f"A: {a}")

        # Print the label and context of each matching row for comparison.
        for _, r in group.iterrows():
            print(f"  id {r['id']:>5} | label: {r[LABEL_COL]} | context: {r['context']}")

        shown += 1

        # Stop once the requested number of duplicate groups has been displayed.
        if shown >= n_groups:
            break

    print("-" * 68 + "\n")


# Runs all cleaning steps and returns the cleaned Circa dataset.
def clean() -> pd.DataFrame:

    # Load the raw Circa TSV file into a pandas DataFrame.
    df = pd.read_csv(RAW, sep="\t")

    # Print the original number of rows before cleaning begins.
    print(f"loaded: {len(df):,} rows")

    # Show duplicate groups first so the rule below is a reasoned decision.
    inspect_duplicates(df)

    # 1. Drop fully identical rows as a safety check.
    # Profiling found none, but this prevents exact copies from remaining.
    before = len(df)
    df = df.drop_duplicates()

    # Show how many exact duplicate rows were removed.
    print(f"exact-duplicate drop      : {len(df):,}  (removed {before - len(df)})")

    # 2. Choose which columns define a duplicate based on the selected rule.
    # With "qa", only question and answer are compared.
    # With "qac", context must also match before a row is considered duplicate.
    subset = ["question-X", "answer-Y"] if DEDUPE_RULE == "qa" \
        else ["question-X", "answer-Y", "context"]

    before = len(df)

    # Keep the first occurrence of each duplicate group and remove the remaining copies.
    df = df.drop_duplicates(subset=subset, keep="first")

    # Print the number of rows removed using the selected duplicate rule.
    print(f"Q-A dedupe (rule={DEDUPE_RULE:>3}) : {len(df):,}  (removed {before - len(df)})")

    # 3. Drop rows with no gold label.
    # These rows are treated as unlabelled because the annotators did not reach agreement.
    # Indirect answers are still kept as long as they have a valid gold label.
    before = len(df)

    # Keep only rows where the gold standard label is available.
    df = df[df[LABEL_COL].notna()]

    # Print how many unlabelled rows were removed.
    print(f"drop unlabelled rows      : {len(df):,}  (removed {before - len(df)})")

    # 4. Remove unnecessary spaces from the beginning and end of the text fields.
    for col in ["context", "question-X", "answer-Y"]:
        df[col] = df[col].astype(str).str.strip()

    # 5. Remove rows where the question or answer became empty after cleaning.
    # This is a safety check to make sure every remaining row contains useful text.
    before = len(df)
    df = df[(df["question-X"] != "") & (df["answer-Y"] != "")]

    # Print how many empty text rows were removed.
    print(f"drop empty-text rows      : {len(df):,}  (removed {before - len(df)})")

    # Return the final cleaned dataset.
    return df


# Run the cleaning process only when this Python file is executed directly.
if __name__ == "__main__":
    df = clean()

    # Create the staging folder if it does not already exist.
    OUT.parent.mkdir(parents=True, exist_ok=True)   # ensure data/staging/ exists

    # Save the cleaned dataset as a Parquet file without adding a pandas index column.
    df.to_parquet(OUT, index=False)

    # Display the output location and final size of the cleaned dataset.
    print(f"\nsaved -> {OUT}  ({len(df):,} rows, {df.shape[1]} columns)")