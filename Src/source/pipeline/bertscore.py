"""BERTScore: each model's rewrite vs the gold rewrite (reference-based metric).

The LLM judge is reference-free; this is the reference-based check Sanket asked
for. For every id it scores the baseline and fine-tuned rewrites against the
gold (teacher) rewrite and reports the mean F1 per model. Higher = closer to
the gold rewrite. The gold rewrite is used ONLY here, never shown to the judge.

Usage (from repo root):
  python -m Src.source.pipeline.bertscore ^
      --gold data/gold_drafts/enron_gold_draft.jsonl ^
      --baseline eval/baseline.jsonl --baseline-name baseline ^
      --finetuned eval/run1.jsonl --finetuned-name run1 ^
      --out eval/enron/bertscore.json
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

REF_FIELD = "rewrite"   # the gold reference rewrite field in the gold file


def _read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _rewrites(path, field="rewrite"):
    out = {}
    for r in _read_jsonl(path):
        rid, rw = r.get("id"), r.get(field)
        if rid and isinstance(rw, str) and rw.strip():
            out[rid] = rw.strip()
    return out


def _score(cands, refs, model_type=None):
    from bert_score import score
    if model_type:
        P, R, F1 = score(cands, refs, model_type=model_type, verbose=False)
    else:
        P, R, F1 = score(cands, refs, lang="en", rescale_with_baseline=True, verbose=False)
    return [round(float(x), 4) for x in F1]


def run(gold_path, models, out_path, model_type=None):
    gold = _rewrites(gold_path, REF_FIELD)
    result = {"gold": str(gold_path),
              "model_type": model_type or "roberta-large (lang=en, rescaled)",
              "per_model": {}}
    per_id = {}
    for name, path in models:
        outs = _rewrites(path)
        ids = sorted(i for i in gold if i in outs)
        if not ids:
            result["per_model"][name] = {"n": 0, "mean_f1": None}
            continue
        f1s = _score([outs[i] for i in ids], [gold[i] for i in ids], model_type)
        for i, f in zip(ids, f1s):
            per_id.setdefault(i, {})[name] = f
        result["per_model"][name] = {"n": len(ids),
                                     "mean_f1": round(statistics.mean(f1s), 4)}
    result["per_id"] = per_id
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"model_type": result["model_type"],
                      "per_model": result["per_model"]}, indent=2))


def main():
    p = argparse.ArgumentParser(description="BERTScore model rewrites vs gold rewrite")
    p.add_argument("--gold", required=True, help="gold jsonl with the reference rewrite")
    p.add_argument("--baseline", required=True)
    p.add_argument("--baseline-name", default="baseline")
    p.add_argument("--finetuned", required=True)
    p.add_argument("--finetuned-name", default="run1")
    p.add_argument("--model", default=None,
                   help="HF model for BERTScore (default roberta-large via lang=en)")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    run(a.gold, [(a.baseline_name, a.baseline), (a.finetuned_name, a.finetuned)],
        a.out, a.model)

if __name__ == "__main__":
    main()