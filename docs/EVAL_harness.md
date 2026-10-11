# Compose eval harness
Decides whether a fine-tuned Compose model ships, by comparing it against the
few-shot baseline with an LLM judge and automatic metrics, and proves the judge
is trustworthy by checking it against human rubric scores.

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
- Replies to questions (Circa): stating the answer a reply clearly implies is
  expected, as in the style guide's Circa example, and leaving it implicit is a
  fault; stating one the reply doesn't settle is a guess. Without this rule the
  judge marked "No, I can't play now" (after "I hurt my knee") as an addition,
  which favoured a model that changes nothing.
- Rubric ID: a hash of the judge model and both prompts (judge.RUBRIC_ID).
  run_judge stamps it on every verdict and won't add to a file made with
  another one; eval_report refuses stale verdicts and redoes stale scores.

## Validating the judge
Nemotron at temperature 0 on NIM is not bit-reproducible, and on borderline
pairs a single verdict is noisy, so the judge's verdicts only count once it
agrees with humans. The pointwise scorer scores each output 0-2 on four
criteria (meaning_kept, clarity, warmth, notes_accurate). On a shared subset
(about 30 outputs, 5 sources per dataset x 2 models, each rated by 2 people)
we compute Spearman between the judge's scores and the human mean. Rho >= 0.6
on the total means we trust the pairwise win rate.

The raters work from blind sheets (rating_sheets.py): no model names, a
different row order for each rater, and the judge's own rubric wording.

## Automatic metrics (eval_metrics.py)
| metric | what it measures |
|---|---|
| json_valid | share of messages with a usable answer (rewrite, notes, meaning) |
| entity_recall | share of the messages' names, organisations, dates, times, amounts, numbers and [TAGS] kept in the rewrites (micro-average) |
| nli_entailment | share of rewrites the NLI model reads as entailed by the message |
| grounded | share that pass the production grounding check |
| added_entity_rate | share of rewrites with an entity the message doesn't have |
| nli_contradiction | share of rewrites the NLI model reads as contradicting the message |
| circa_direct_rate | Circa: share of rewritten replies the Circa classifier reads as direct |
| circa_answer_stated_rate | Circa: share of rewritten replies that open with the answer ("Yes, ...", "No, ...", "I can't ..."), as the style guide's example does; the classifier above is a weak hint |
| politeness_drop_rate | share where the politeness band falls (high -> medium, ...) |
| politeness_to_low_rate | share where a message that wasn't blunt became blunt |
| length_ratio | median words(rewrite) / words(message), the reply for Circa |
| bertscore_f1 | mean F1 vs the gold rewrite, only for datasets whose gold is fully human-checked |
| notes_accurate, rubric_total | the judge's pointwise scores, mean over the outputs (from `eval_report score`) |

The entity and NLI rules are the grounding check's own (which imports them
from the training filter), so the eval measures what serving enforces. The
first four count a message with no usable answer as a failure, so a model
can't raise them by failing; the rest are over the answers it gave.

## The ship rule (ship_check.py)
On the "all" rows of results.csv (every dataset pooled), the fine-tuned model
ships if:
1. it beats the baseline with the judge: more wins than losses over the pairs
   both orders agreed on;
2. its entity_recall is no more than 2 points below the baseline's;
3. its nli_entailment is no more than 2 points below the baseline's.

The verdict only counts once the judge is validated (judge_validation.json,
rho >= 0.6) and the gold is locked and unchanged (data/gold/LOCK.json);
until then it says UNDECIDED, and `--preview` shows what it would be. Exit
status: 0 the fine-tuned model ships, 1 the baseline ships, 2 undecided. Both
models' numbers stay in results.csv for the report.

## Files
- judge.py           pairwise judge (judge_pair) and pointwise scorer (score_output)
- run_judge.py       batch the pairwise judge over a source + two output files
- validate_judge.py  Spearman of judge vs human scores
- bertscore.py       BERTScore vs the gold rewrite
- eval_metrics.py    the automatic metrics
- eval_report.py     rubric scoring step; results.csv, results_meta.json, worst20_<model>.md
- rating_sheets.py   blind sheets for the human raters, and collecting them
- ship_check.py      the ship rule
- eval/human_scores.csv  the human scores, written by `rating_sheets collect`

## Running it
Once, on a laptop:

    pip install -r Src/source/pipeline/requirements.txt \
        -r Src/source/pipeline/requirements-compose.txt \
        -r Src/source/pipeline/requirements-eval.txt

1. Predictions, for each dataset (enron, stanford, circa) and model, with the
   model served by llama-server (see compose_client.py's docstring). The baseline runs
   with --few-shot, a fine-tuned model without:

       python -m Src.source.pipeline.compose_client --few-shot --temperature 0 \
           --input data/gold/enron_gold.jsonl --url http://127.0.0.1:8080 \
           --out eval/enron/baseline.jsonl
       python -m Src.source.pipeline.compose_client --temperature 0 \
           --input data/gold/enron_gold.jsonl --url http://127.0.0.1:8081 \
           --out eval/enron/run2.jsonl

2. The pairwise judge, for each dataset:

       python -m Src.source.pipeline.run_judge --source data/gold/enron_gold.jsonl \
           --a eval/enron/baseline.jsonl --a-name baseline \
           --b eval/enron/run2.jsonl --b-name run2 --out eval/enron/baseline_vs_run2

3. The rubric scores, for change-note accuracy (one judge call per output):

       python -m Src.source.pipeline.eval_report score --models baseline run2

4. The human check of the judge: make the sheets, fill them in, collect them,
   then validate:

       python -m Src.source.pipeline.rating_sheets make --finetuned run2 --raters <name> <name>
       python -m Src.source.pipeline.rating_sheets collect
       python -m Src.source.pipeline.validate_judge --human eval/human_scores.csv \
           --source data/gold/{enron,stanford,circa}_gold.jsonl \
           --baseline eval/{enron,stanford,circa}/baseline.jsonl \
           --finetuned eval/{enron,stanford,circa}/run2.jsonl \
           --out eval/judge_validation.json

5. The results and the decision:

       python -m Src.source.pipeline.eval_report report --models run2
       python -m Src.source.pipeline.ship_check --finetuned run2
