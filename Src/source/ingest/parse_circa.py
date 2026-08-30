import pandas as pd
from pathlib import Path

# Make console output readable and untruncated, so the exploration is fully
# visible for review rather than cut off with "...".
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 160)
pd.set_option("display.max_colwidth", 60)

RAW = Path("data/raw/circa-data.tsv")   # path relative to repo root
LABEL_COL = "goldstandard1"             # strict label aggregation (primary)
ALT_LABEL_COL = "goldstandard2"         # relaxed aggregation (for comparison)
DIRECT_LABELS = ["Yes", "No"]           # team's working definition of "direct"


def load() -> pd.DataFrame:
    """Read the tab-separated Circa file into a DataFrame (fail loudly if missing)."""
    if not RAW.exists():
        raise FileNotFoundError(
            f"Cannot find {RAW}. Run from the repo root and confirm the TSV "
            f"is in data/raw/."
        )
    df = pd.read_csv(RAW, sep="\t")  # TSV => tab separator
    print(f"Loaded {RAW}  ->  {df.shape[0]:,} rows x {df.shape[1]} columns\n")
    return df


def explore_structure(df: pd.DataFrame) -> None:
    """1. What columns exist, their data types, and how populated they are."""
    print("=" * 70 + "\n1. STRUCTURE & DATA TYPES\n" + "=" * 70)
    df.info()  # dtypes + non-null counts in a single compact view
    print("\nFirst 5 rows:")
    print(df.head())
    print("\nColumn roles for our pipeline:")
    print("  question-X    -> the yes/no QUESTION")
    print("  answer-Y      -> the INDIRECT ANSWER")
    print("  goldstandard1 -> gold INTERPRETATION label (strict)  [primary]")
    print("  goldstandard2 -> gold interpretation label (relaxed)")
    print("  id            -> unique key -> becomes external_ref in MESSAGE\n")


def explore_missing(df: pd.DataFrame) -> None:
    """2. Where data is missing and how much — this drives cleaning choices."""
    print("=" * 70 + "\n2. MISSING VALUES\n" + "=" * 70)
    summary = pd.DataFrame({
        "nulls": df.isnull().sum(),
        "pct":   (df.isnull().mean() * 100).round(2),
    })
    print(summary)
    print(
        f"\nInterpretation: {LABEL_COL} nulls are typically rows where annotators "
        f"could NOT agree on a meaning — i.e. genuinely ambiguous answers. For a "
        f"project about ambiguity these are meaningful, not just noise, so we flag "
        f"them for a team decision rather than deleting them reflexively.\n"
    )


def explore_duplicates(df: pd.DataFrame) -> None:
    """3. Check for repeated rows / ids BEFORE any dedupe in the cleaning stage."""
    print("=" * 70 + "\n3. DUPLICATES\n" + "=" * 70)
    print("Fully-identical rows           :", df.duplicated().sum())
    print("Duplicate ids                  :", df["id"].duplicated().sum())
    print("Duplicate (question, answer)   :",
          df.duplicated(subset=["question-X", "answer-Y"]).sum(), "\n")


def explore_text(df: pd.DataFrame) -> None:
    """4. Length profile of the text fields we will actually feed the model."""
    print("=" * 70 + "\n4. TEXT LENGTH (question & answer)\n" + "=" * 70)
    for col in ["question-X", "answer-Y"]:
        chars = df[col].astype(str).str.len()
        words = df[col].astype(str).str.split().str.len()
        print(f"\n{col}:")
        print(f"  chars -> min {chars.min()}, mean {chars.mean():.1f}, max {chars.max()}")
        print(f"  words -> min {words.min()}, mean {words.mean():.1f}, max {words.max()}")
    print()


def explore_labels(df: pd.DataFrame) -> None:
    """5. Distribution of BOTH gold columns + how often they agree."""
    print("=" * 70 + "\n5. LABEL DISTRIBUTION\n" + "=" * 70)
    print(f"{LABEL_COL} (strict), nulls excluded:")
    print(df[LABEL_COL].value_counts(normalize=True).round(3))
    print(f"\n{ALT_LABEL_COL} (relaxed), nulls excluded:")
    print(df[ALT_LABEL_COL].value_counts(normalize=True).round(3))

    # How much does the strict-vs-relaxed choice actually change things?
    both = df.dropna(subset=[LABEL_COL, ALT_LABEL_COL])
    agree = (both[LABEL_COL] == both[ALT_LABEL_COL]).mean()
    print(f"\nStrict vs relaxed agree on {agree:.1%} of doubly-labelled rows "
          f"— shows how much the aggregation choice matters.\n")


def explore_directness(df: pd.DataFrame) -> None:
    """6. The DERIVED directness split under 3 definitions — locate the ~82/18."""
    print("=" * 70 + "\n6. DIRECTNESS SPLIT (derived — depends on definition)\n" + "=" * 70)
    labelled = df[df[LABEL_COL].notna()]  # rows that actually carry a label

    # V0: clear Yes/No, nulls KEPT (a null counts as indirect).
    v0 = df[LABEL_COL].isin(DIRECT_LABELS)
    print("V0  clear Yes/No, nulls KEPT as indirect:")
    print(v0.value_counts(normalize=True).round(3))

    # A: clear Yes/No, nulls DROPPED first.
    vA = labelled[LABEL_COL].isin(DIRECT_LABELS)
    print("\nA   clear Yes/No, nulls DROPPED:")
    print(vA.value_counts(normalize=True).round(3))

    # B: 'probably' labels also count as direct, nulls DROPPED.
    probably = ["Yes", "No", "Probably yes / sometimes yes", "Probably no"]
    vB = labelled[LABEL_COL].isin(probably)
    print("\nB   Yes/No + 'probably' = direct, nulls DROPPED:")
    print(vB.value_counts(normalize=True).round(3))

    print("\nNote: 'directness' is not a raw column — it is derived, so the split "
          "is only meaningful stated ALONGSIDE its definition. Record which one "
          "the team adopts.\n")


def show_examples(df: pd.DataFrame, n: int = 3) -> None:
    """7. Print a few complete rows so the real data is visible, not just stats."""
    print("=" * 70 + "\n7. SAMPLE RECORDS\n" + "=" * 70)
    for _, row in df.head(n).iterrows():
        print(f"[id {row['id']}]")
        print(f"  context : {row['context']}")
        print(f"  question: {row['question-X']}")
        print(f"  answer  : {row['answer-Y']}")
        print(f"  label   : {row[LABEL_COL]}\n")


if __name__ == "__main__":
    df = load()
    explore_structure(df)     # 1. shape, dtypes, columns
    explore_missing(df)       # 2. missing-value analysis
    explore_duplicates(df)    # 3. duplicate check
    explore_text(df)          # 4. text length profile
    explore_labels(df)        # 5. label distribution + gold1/gold2 agreement
    explore_directness(df)    # 6. directness split (V0 / A / B)
    show_examples(df)         # 7. full sample records