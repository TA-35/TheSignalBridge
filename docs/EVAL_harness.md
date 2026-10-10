# Compose eval harness
Decides whether a fine-tuned Compose model ships, by comparing it against the
few-shot baseline with an LLM judge, and proves the judge is trustworthy by
checking it against human rubric scores.

## What it compares
- A = few-shot baseline (base Qwen with the compose examples in the prompt).
- B = fine-tuned model (trained without the examples).
- Both run over the same gold source messages, one output each (meaning,
  rewrite, notes). The teacher (DeepSeek) is not in the comparison.

## The judge
- Model: nvidia/nemotron-3-super-120b-a12b on NVIDIA NIM, temperature 0. A
  different model family from the teacher (DeepSeek) and the student (Qwen),
  so it cannot favour its own style.
- Reference-free: the judge sees the source, the two outputs and the rubric,
  never the gold rewrite (the gold drafts were written by the teacher, which
  would bias the judge toward the fine-tuned model). The gold rewrite is used
  only for BERTScore, elsewhere.
- Rubric: the "Spot-check: pass or fail" criteria from COMPOSE_STYLE_GUIDE.md.
- Position-bias control: every pair is judged twice with the outputs swapped.
  A model wins only if it is picked in both orderings; a disagreement is
  recorded as no_decision, which also measures the judge's position bias.

## Validating the judge
Nemotron at temperature 0 on NIM is not bit-reproducible, and on borderline
pairs a single verdict is noisy, so the judge's verdicts only count once it
agrees with humans. The pointwise scorer scores each output 0-2 on four
criteria (meaning_kept, clarity, warmth, notes_accurate). On a shared subset
(about 30 outputs, 5 sources per dataset x 2 models, each rated by 2 people)
we compute Spearman between the judge's scores and the human mean. Rho >= 0.6
on the total means we trust the pairwise win rate.

## Files
- judge.py           pairwise judge (judge_pair) and pointwise scorer (score_output)
- run_judge.py       batch the pairwise judge over a source + two output files
- validate_judge.py  Spearman of judge vs human scores
- eval/human_scores.csv  the human rating sheet

## Running it
Generate the two output files with compose_client (baseline with --few-shot,
the fine-tuned model without), then:

    python -m Src.source.pipeline.run_judge --source <gold.jsonl> \
        --a eval/baseline.jsonl --a-name baseline \
        --b eval/run1.jsonl --b-name run1 --out eval/<dataset>

    python -m Src.source.pipeline.validate_judge --human eval/human_scores.csv \
        --source <gold.jsonl> --baseline eval/baseline.jsonl \
        --finetuned eval/run1.jsonl --out eval/<dataset>/judge_validation.json