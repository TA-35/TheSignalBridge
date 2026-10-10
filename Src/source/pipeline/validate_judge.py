"""Validate the LLM judge against human rubric scores.

Runs the pointwise judge over the same (id, model) outputs the humans scored,
then computes Spearman per criterion and on the total. Rho >= 0.6 on the total
means we trust the judge's pairwise win rate.

human_scores.csv columns:
  id, dataset, model (baseline|finetuned), rater,
  meaning_kept, clarity, warmth, notes_accurate (each 0-2), comment

Usage (from repo root):
  python -m Src.source.pipeline.validate_judge \
      --human eval/human_scores.csv \
      --source data/gold_drafts/enron_gold_draft.jsonl \
      --baseline eval/baseline.jsonl --finetuned eval/run1.jsonl \
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

from .judge import score_output, SCORE_CRITERIA, JudgeError

TRUST_THRESHOLD = 0.6  # Minimum correlation needed to trust the judge


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:  # Open the JSONL file
        return [json.loads(line) for line in f if line.strip()]  # Read each non-empty line as a JSON record


def _outputs(path):
    out = {}  # Store model outputs using their IDs

    for r in _read_jsonl(path):  # Go through each record in the output file
        if r.get("id") and isinstance(r.get("rewrite"), str) and r["rewrite"].strip():  # Keep records with a valid ID and non-empty rewrite
            out[r["id"]] = {
                "meaning": r.get("meaning") or {},  # Get the extracted meaning or use an empty dictionary
                "rewrite": r["rewrite"].strip(),  # Get the rewrite without extra spaces
                "notes": r.get("notes") or []  # Get the notes or use an empty list
            }

    return out  # Return all valid model outputs


def run(human_csv, source_path, baseline_path, finetuned_path, out_path):
    from scipy.stats import spearmanr  # Import the function used to calculate Spearman correlation

    source = {
        r["id"]: r for r in _read_jsonl(source_path)
    }  # Load original messages and store them by ID

    outputs = {
        "baseline": _outputs(baseline_path),  # Load outputs from the baseline model
        "finetuned": _outputs(finetuned_path)  # Load outputs from the fine-tuned model
    }

    human = defaultdict(list)  # Store human ratings for each record and model

    with open(human_csv, encoding="utf-8", newline="") as f:  # Open the CSV containing human scores
        for row in csv.DictReader(f):  # Read each row using its column names
            key = (row["id"].strip(), row["model"].strip())  # Create a key using the record ID and model name

            try:
                human[key].append({
                    c: float(row[c]) for c in SCORE_CRITERIA
                })  # Convert human scores into numbers and store them

            except (KeyError, ValueError):
                continue  # Skip rows with missing or invalid scores

    keys = [
        k for k in human
        if k[0] in source and k[0] in outputs.get(k[1], {})
    ]  # Keep only records available in the source, model outputs, and human ratings

    if not keys:
        raise SystemExit(
            "no usable rows: check that ids/models in human_scores.csv "
            "match the source and output files"
        )  # Stop if no matching records are available for validation

    def score(k):
        rid, model = k  # Get the record ID and model name

        try:
            return k, score_output(
                source[rid]["source"],
                source[rid].get("signals"),
                outputs[model][rid]
            ), None  # Get the judge scores and return no error if successful

        except JudgeError as exc:
            return k, None, str(exc)  # Return the error message if the judge call fails

    judged, failed = {}, []  # Store successful judge scores and failed requests separately

    with ThreadPoolExecutor(max_workers=5) as pool:  # Run up to five judge requests at the same time
        for k, sc, err in pool.map(score, keys):  # Get the result of each scoring request

            if sc is None:
                failed.append({
                    "id": k[0],  # Store the ID of the failed record
                    "model": k[1],  # Store which model's output failed
                    "error": err  # Store the reason for the failure
                })

            else:
                judged[k] = sc  # Save the scores if the judge call was successful

    keys = [k for k in keys if k in judged]  # Keep only records that were scored successfully

    if failed:
        print(f"WARNING: {len(failed)} score call(s) failed, excluded from Spearman")  # Show how many failed scores were excluded

    if not keys:
        raise SystemExit("every score call failed; nothing to correlate")  # Stop if there are no successful judge scores

    human_mean = {
        k: {
            c: statistics.mean(r[c] for r in human[k])
            for c in SCORE_CRITERIA
        }
        for k in keys
    }  # Calculate the average human score for each criterion across all raters

    def corr(h, j):
        if len(h) < 3:
            return None, None  # Return no correlation if fewer than three scored outputs are available

        rho, p = spearmanr(h, j)  # Calculate Spearman correlation and its p-value

        return (
            None if rho != rho else round(float(rho), 3),  # Return the rounded correlation or None if undefined
            None if p != p else round(float(p), 3)  # Return the rounded p-value or None if undefined
        )

    result = {
        "n": len(keys),  # Store the number of successfully scored outputs
        "failed_scores": len(failed),  # Store the number of judge requests that failed
        "trust_threshold": TRUST_THRESHOLD,  # Store the minimum required correlation
        "per_criterion": {}  # Store correlation results for each scoring criterion
    }

    for c in SCORE_CRITERIA:  # Calculate correlation separately for each criterion
        rho, p = corr(
            [human_mean[k][c] for k in keys],  # Get the average human scores for this criterion
            [getattr(judged[k], c) for k in keys]  # Get the judge scores for the same criterion
        )

        result["per_criterion"][c] = {
            "rho": rho,  # Store the correlation between human and judge scores
            "p": p  # Store the p-value for this correlation
        }

    rho, p = corr(
        [sum(human_mean[k].values()) for k in keys],  # Calculate the total human score for each output
        [judged[k].total for k in keys]  # Get the total judge score for each output
    )

    result["total"] = {
        "rho": rho,  # Store the correlation between total human and judge scores
        "p": p  # Store the p-value for the total correlation
    }

    result["trust_judge"] = bool(rho is not None and rho >= TRUST_THRESHOLD)  # Trust the judge if total correlation is at least 0.6

    if failed:
        result["failures"] = failed  # Include the failed record details if any requests failed

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)  # Create the output folder if it does not exist

    Path(out_path).write_text(
        json.dumps(result, indent=2),
        encoding="utf-8"
    )  # Save all validation results and any failure details to a JSON file

    print(
        json.dumps({k: v for k, v in result.items() if k != "failures"}, indent=2)
    )  # Display the summary without printing individual failure details


def main():
    p = argparse.ArgumentParser(
        description="Validate the judge against human scores"
    )  # Create the command-line argument parser

    p.add_argument("--human", required=True)  # Get the CSV file containing human ratings
    p.add_argument("--source", required=True)  # Get the original source messages
    p.add_argument("--baseline", required=True)  # Get the baseline model outputs
    p.add_argument("--finetuned", required=True)  # Get the fine-tuned model outputs
    p.add_argument("--out", required=True)  # Get the file path for saving validation results

    a = p.parse_args()  # Read the arguments given in the command line

    run(a.human, a.source, a.baseline, a.finetuned, a.out)  # Run validation using the provided files

if __name__ == "__main__":
    main()  # Run the script when executed directly