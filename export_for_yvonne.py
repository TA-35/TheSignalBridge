# export_for_yvonne.py
# pulls just the body column from your 300-row eval set into a small
# csv to send yvonne - she runs her politeness model on these same
# messages, sends the scores back, and that's what feeds the
# correlation check in enron_evaluate_and_predict.py
#
# run once: python3 export_for_yvonne.py

from pathlib import Path
import pandas as pd

EVAL_HUMAN_FILE = Path("data/processed/enron_tone_eval_human.csv")
OUTPUT_FILE = Path("data/processed/messages_for_yvonne.csv")


def main():
    if not EVAL_HUMAN_FILE.exists():
        print(f"cant find {EVAL_HUMAN_FILE}")
        return

    df = pd.read_csv(EVAL_HUMAN_FILE)

    # just body - she doesn't need message_id, human_label etc, keeps
    # the file simple for her to work with and matches what the
    # correlation check merges on (the "body" column)
    out = df[["body"]].copy()
    out.to_csv(OUTPUT_FILE, index=False)

    print(f"exported {len(out)} messages to {OUTPUT_FILE}")
    print("send this file to yvonne - ask her to add a 'politeness_score' column")
    print("and save the result as data/processed/stanford_politeness_output.csv")


if __name__ == "__main__":
    main()
