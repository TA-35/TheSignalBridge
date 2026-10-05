# Enron Tone Classifier (Final Build)

## What it's for

Every message that goes through the rewrite pipeline gets a tone label: neutral, casual or formal. The label and its confidence go into the LLM prompt through `Src/source/pipeline/adapters/tone.py`, so the rewrite knows what register the original was written in.

## The labels

| Label | What it looks like |
|---|---|
| neutral | Everyday work writing. Plain and to the point, not stiff and not chatty. |
| casual | Relaxed and friendly. Slang, jokes, emoticons, chatty contractions. Informal messages count as casual. |
| formal | Careful, polite business writing. Full greetings and sign-offs, official or deferential wording. |

We dropped terse for the final build after the team call in October 2026, and folded informal into casual.

## Model

It's `distilbert-base-uncased` with a 3-class head on top. We trained it for 2 epochs with a learning rate of 3e-5, batch size 32 and a max length of 128 tokens. The loss is weighted by class, because otherwise the model mostly learns neutral and ignores the two smaller classes. It needs torch and transformers to run.

## Data

We started from the cleaned Enron corpus (`data/staging/enron_cleaned.csv`, described in `docs/DATA_CARD_ENRON.md`), kept only the message body with quoted replies, forwards and signatures cut off, and kept messages between 5 and 120 words.

From there we sampled 35,000 emails and gave casual-looking ones extra weight, since casual is rare in Enron and would otherwise get drowned out.

Labelling 35,000 emails by hand wasn't realistic, so we had Claude (`claude-haiku-4-5-20251001`) label them, 20 emails per request, using the definitions above. Before the full run we labelled 200 and read through a sample to make sure the labels made sense. The final mix was 20,190 neutral (58%), 9,586 casual (27%) and 5,224 formal (15%).

## Keeping the test set honest

Exact duplicates and repeated threads were removed before sampling, and the 300 hand-labelled rows from Iteration 2 were kept out completely. The train/test split is 90/10, stratified by label, with seed 42.

## How to train it

From the project root:

```bash
python3 Src/source/model/tone/enron_register.py prep
python3 Src/source/model/tone/enron_register.py label --limit 200   # try a small batch first
python3 Src/source/model/tone/enron_register.py label               # needs ANTHROPIC_API_KEY
python3 Src/source/model/tone/enron_register.py train
```

The weights, tokenizer, `metrics.json` and `classification_report.txt` end up in `models/enron_register_distilbert/`. Training took about 33 minutes on an M-series Mac.

## How to use it

```bash
python3 Src/source/model/tone/enron_register.py predict "hey can u send that over lol"
```

That prints `{"tone": "casual", "tone_scores": {"neutral": 0.006, "casual": 0.993, "formal": 0.001}}`.

## Reading the output

The label tells you how the message is written, not whether it's polite or clear. Politeness and circa cover those. The confidence is the model's own probability, which isn't the same as how often it's right for that class. Since the model calls too many emails formal, the pipeline adapter caps formal confidence at 0.6 and explains why in the note.

## Results (3 October 2026)

These are on the 3,500 emails we held back, scored against Claude's labels rather than human ones.

| | Precision | Recall | F1 | Count |
|---|---:|---:|---:|---:|
| neutral | 0.887 | 0.766 | 0.822 | 2,019 |
| casual | 0.835 | 0.848 | 0.841 | 959 |
| formal | 0.575 | 0.860 | 0.689 | 522 |
| accuracy | | | 0.803 | 3,500 |
| macro average | 0.765 | 0.825 | 0.784 | 3,500 |

Confusion matrix (rows are the true label, columns the prediction, in the order neutral, casual, formal):
[[1547 156 316]
[ 130 813 16]
[ 68 5 449]]

The training loss started around 0.90 and was down to about 0.32 by the end of the second epoch.

A few quick checks by hand:

| Message | Label | Confidence |
|---|---|---:|
| "hey can u send that over lol" | casual | 0.993 |
| "Dear Mr Smith, I would appreciate your confirmation of the meeting time. Kind regards" | formal | 0.994, capped to 0.6 in the adapter |
| "Please send me the updated figures by Friday." | neutral | 0.894 |

### How it compares with Iteration 2

The Iteration 2 model (neutral, casual, terse, trained on rule-based labels) got 72% on our 300 hand-labelled rows, but it only caught 30% of casual messages and called most of them neutral. This model catches 85% of casual. The two numbers aren't a fair head-to-head, though, since the labels and the reference data are different.

### Things to keep in mind

- The test labels come from Claude, so these scores tell you how well the model agrees with Claude, not with people. We don't have a human-labelled test set for these three labels yet.
- Formal gets over-used. 316 of the 2,019 neutral test emails were called formal, which is why formal precision is only 0.58. Polite but plain business emails sit right on that line, and the class weighting nudges the model towards formal.
- Casual and formal almost never get mixed up (16 and 5 errors), so the model gets the two ends right. Nearly all the mistakes involve neutral.

## Limitations

- Enron is American office email from 1999 to 2002, so newer styles like chat messages or lots of emoji may not be read well.
- Very short messages don't give the model much to go on.
- The weights are around 250MB, too big for git. They live on the team Drive under Iteration Build > Models. Unzip them into `models/` so the folder is `models/enron_register_distilbert/`. The server needs that folder too, otherwise tone just comes back as "unknown".

## Use of AI

Claude (`claude-haiku-4-5-20251001`) wrote the training labels. The cleaning, training and evaluation code is our own.

## What we'd do next

1. Hand-label around 150 messages (about 50 per label) so we can measure the model against people, not just Claude.
2. Tune the formal threshold on a validation split, giving up a little formal recall for better precision.
3. Calibrate the confidence scores so they match how often the model is actually right.
