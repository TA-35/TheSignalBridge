"""Validate the LLM judge against human rubric scores (step 4).

Runs the pointwise judge over the same (id, model) outputs the humans scored,
then computes Spearman per criterion and on the total. Rho >= 0.6 on the total
means we trust the judge's pairwise win rate.

human_scores.csv columns:
  id, dataset, model (baseline|finetuned), rater,
  meaning_kept, clarity, warmth, notes_accurate (each 0-2), comment

Usage (from repo root):
  python -m Src.source.pipeline.validate_judge ^
      --human eval/human_scores.csv ^
      --source data/gold_drafts/enron_gold_draft.jsonl ^
      --baseline eval/baseline.jsonl --finetuned eval/run1.jsonl ^
      --out eval/enron/judge_validation.json
"""

from __future__ import annotations
import argparse
import csv
import json
import statistics
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .judge import score_output, SCORE_CRITERIA

TRUST_THRESHOLD = 0.6  # Minimum correlation needed to trust the judge

def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:  # Open the JSONL file
        return [json.loads(line) for line in f if line.strip()]  # Read all non-empty lines as JSON records

def _outputs(path):
    out = {}  # Store model outputs using their IDs

    for r in _read_jsonl(path):  # Go through each record in the output file
        if r.get("id") and isinstance(r.get("rewrite"), str) and r["rewrite"].strip():  # Keep records with a valid ID and non-empty rewrite
            out[r["id"]] = {
                "meaning": r.get("meaning") or {},  # Get the meaning or use an empty dictionary
                "rewrite": r["rewrite"].strip(),  # Get the rewrite without extra spaces
                "notes": r.get("notes") or []  # Get the notes or use an empty list
            }

    return out  # Return all valid model outputs

def run(human_csv, source_path, baseline_path, finetuned_path, out_path):
    from scipy.stats import spearmanr  # Import the function used to calculate Spearman correlation

    source = {
        r["id"]: r for r in _read_jsonl(source_path)
    }  # Load the original source records and store them by ID

    outputs = {
        "baseline": _outputs(baseline_path),  # Load the baseline model outputs
        "finetuned": _outputs(finetuned_path)  # Load the fine-tuned model outputs
    }

    human = defaultdict(list)  # Store all human ratings for each ID and model

    with open(human_csv, encoding="utf-8", newline="") as f:  # Open the CSV containing human scores
        for row in csv.DictReader(f):  # Read each row as a dictionary using the column names
            key = (row["id"].strip(), row["model"].strip())  # Create a key using the record ID and model name

            try:
                human[key].append({
                    c: float(row[c]) for c in SCORE_CRITERIA
                })  # Convert the human scores into numbers and store them

            except (KeyError, ValueError):
                continue  # Skip rows with missing or invalid scores

    keys = [
        k for k in human
        if k[0] in source and k[0] in outputs.get(k[1], {})
    ]  # Keep only records that exist in the source, model outputs, and human scores

    if not keys:
        raise SystemExit(
            "no usable rows: check that ids/models in human_scores.csv "
            "match the source and output files"
        )  # Stop if no matching records are available for evaluation

    def score(k):
        rid, model = k  # Get the record ID and model name

        return k, score_output(
            source[rid]["source"],
            source[rid].get("signals"),
            outputs[model][rid]
        )  # Ask the LLM judge to score the model output using the original message and signals

    judged = {}  # Store the scores given by the LLM judge

    with ThreadPoolExecutor(max_workers=5) as pool:  # Run up to five scoring tasks at the same time
        for k, sc in pool.map(score, keys):  # Get each record's ID/model key and its judge scores
            judged[k] = sc  # Save the judge scores for this record and model

    human_mean = {
        k: {
            c: statistics.mean(r[c] for r in human[k])
            for c in SCORE_CRITERIA
        }
        for k in keys
    }  # Calculate the average human score for each criterion across all raters

    def corr(h, j):
        if len(h) < 3:
            return None, None  # Return no correlation if fewer than three records are available

        rho, p = spearmanr(h, j)  # Calculate correlation and p-value between human and judge scores

        return (
            None if rho != rho else round(float(rho), 3),  # Return rounded correlation or None if undefined
            None if p != p else round(float(p), 3)  # Return rounded p-value or None if undefined
        )

    result = {
        "n": len(keys),  # Store the number of ID/model pairs being evaluated
        "trust_threshold": TRUST_THRESHOLD,  # Store the minimum required correlation
        "per_criterion": {}  # Store correlation results for each scoring criterion
    }

    for c in SCORE_CRITERIA:  # Calculate correlation separately for each criterion
        rho, p = corr(
            [human_mean[k][c] for k in keys],  # Get the average human scores for this criterion
            [getattr(judged[k], c) for k in keys]  # Get the LLM judge scores for the same criterion
        )

        result["per_criterion"][c] = {
            "rho": rho,  # Store the correlation between human and judge scores
            "p": p  # Store the p-value for this correlation
        }

    rho, p = corr(
        [sum(human_mean[k].values()) for k in keys],  # Calculate the total human score for each output
        [judged[k].total for k in keys]  # Get the total LLM judge score for each output
    )

    result["total"] = {
        "rho": rho,  # Store the correlation between total human and judge scores
        "p": p  # Store the p-value for the total correlation
    }

    result["trust_judge"] = bool(rho is not None and rho >= TRUST_THRESHOLD)  # Trust the judge if total correlation is at least 0.6
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)  # Create the output folder if it does not exist
    Path(out_path).write_text(
        json.dumps(result, indent=2),
        encoding="utf-8"
    )  # Save the validation results in a readable JSON file
    print(json.dumps(result, indent=2))  # Display the final validation results

def main():
    p = argparse.ArgumentParser(
        description="Validate the judge against human scores"
    )  # Create the command-line argument parser

    p.add_argument("--human", required=True)  # Get the CSV file containing human ratings
    p.add_argument("--source", required=True)  # Get the file containing original messages
    p.add_argument("--baseline", required=True)  # Get the baseline model outputs
    p.add_argument("--finetuned", required=True)  # Get the fine-tuned model outputs
    p.add_argument("--out", required=True)  # Get the path for saving validation results
    a = p.parse_args()  # Read the arguments provided in the command line
    run(a.human, a.source, a.baseline, a.finetuned, a.out)  # Run the judge validation using the provided files

if __name__ == "__main__":
    main()  # Run the script when executed directly