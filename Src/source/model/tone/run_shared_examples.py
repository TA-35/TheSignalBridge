# run_shared_examples.py
# runs predict() on the 20 shared example messages the team is using to
# compare all three paths (tone/politeness/intent), formats the output
# for handoff.
#
# put your 20 messages in data/processed/shared_examples.csv with a
# single "body" column (or "message" - both are checked), then run:
#   python3 run_shared_examples.py
#
# writes data/processed/tone_predictions_shared_examples.csv and also
# prints a readable version to the terminal for pasting into a doc/slack

from pathlib import Path
import pandas as pd

from enron_evaluate_and_predict import predict

INPUT_FILE = Path("data/processed/shared_examples.csv")
OUTPUT_FILE = Path("data/processed/tone_predictions_shared_examples.csv")


def main():
    if not INPUT_FILE.exists():
        print(f"cant find {INPUT_FILE}")
        print("create this file with a 'body' column containing the 20 shared messages")
        return

    df = pd.read_csv(INPUT_FILE)

    body_col = "body" if "body" in df.columns else ("message" if "message" in df.columns else None)
    if body_col is None:
        print("need a 'body' or 'message' column in the input file")
        return

    results = []
    for i, body in enumerate(df[body_col]):
        pred = predict(body)
        results.append({
            "example_num": i + 1,
            "body_preview": (body[:80] + "...") if isinstance(body, str) and len(body) > 80 else body,
            "model": pred["model"],
            "label": pred["label"],
            "confidence": pred["confidence"],
            "note": pred["note"],
        })

    out_df = pd.DataFrame(results)
    out_df.to_csv(OUTPUT_FILE, index=False)

    print(f"wrote predictions to {OUTPUT_FILE}\n")
    print("readable version below (for pasting into a doc/slack):\n")
    for r in results:
        print(f"[{r['example_num']}] \"{r['body_preview']}\"")
        print(f"    tone: {r['label']} (confidence {r['confidence']}) - {r['note']}\n")


if __name__ == "__main__":
    main()
