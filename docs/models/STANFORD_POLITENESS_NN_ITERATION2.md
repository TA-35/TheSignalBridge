# Iteration 2 English Politeness Neural Network

## Goal

Replace the same-day Iteration 1 MVP with a planned model that uses every data source in the Stanford Politeness Corpus
folder, generalises to unseen messages, and still runs with NumPy only.

## What was built

Two networks, trained in sequence (4 October 2026):

1. **Teacher**: RoBERTa-base fine-tuned for regression on the 7,666 training requests (3 epochs, mean pooling, Huber loss).
   About 480 MB and needs PyTorch, so it is used offline only and is not stored in this folder.
2. **Shipped model**: a small text CNN (word embeddings, convolutions of width 1 to 4, max and mean pooling, one hidden
   layer) trained to reproduce the teacher. 6.6 MB, NumPy-only inference, same output contract as Iteration 1.

## How each data source was used

| Source | Use |
|---|---|
| 10,956 annotated requests (`stanford_politeness_features.csv`) | Supervised target (`Normalized Score`), same 70/15/15 grouped split as Iteration 1 |
| Five raw annotator scores per request | Per-request agreement converted to a sample weight, replacing the single 0.55 flag weight; also used to estimate the accuracy ceiling |
| 21 politeness-strategy features | Tested as extra inputs. They help the bag-of-words baseline slightly and add nothing to RoBERTa (validation Pearson 0.609 with, 0.617 without), so the shipped model does not need spaCy at run time |
| ~409,000 unlabelled requests (`*.requests.csv`) | Cleaned with the same pipeline functions; 179,607 were scored by the teacher and used to train the shipped model |

## Leakage control

- Split is identical to Iteration 1: identical normalised messages stay in one split.
- Every annotated text (train, validation and test) was removed from the unlabelled pool before teacher scoring. Verified:
  0 validation or test texts appear in the pool.
- All choices (architecture, epochs, level cut-offs) were made on validation. The test split was scored once, at the end.

## Results

Level cut-offs for every model below are the tertiles of that model's validation predictions, so the comparison is
like for like. "Binary" is polite versus impolite on requests in the top and bottom quartile of human scores, the task
used in the original paper.

| Model | Train Pearson | Validation Pearson | Test Pearson | Test MAE | Test 3-class accuracy | Test binary accuracy |
|---|---:|---:|---:|---:|---:|---:|
| Iteration 1 hashed MLP | 0.530 | 0.450 | 0.411 | 0.511 | 48.4% | 74.3% |
| TF-IDF ridge + 21 features (baseline) | 0.822 | 0.523 | 0.484 | 0.484 | 50.1% | 74.4% |
| RoBERTa teacher (offline) | 0.753 | 0.617 | 0.607 | 0.448 | 56.0% | 82.4% |
| **Iteration 2 shipped CNN** | 0.707 | 0.585 | **0.560** | 0.461 | **55.5%** | **81.3%** |

Test 95% bootstrap intervals for the shipped model: Pearson 0.523 to 0.599, 3-class accuracy 53.1% to 57.8%.
With the cut-offs Iteration 1 actually shipped (training-label tertiles), its test 3-class accuracy was 46.0%.

### By source (test split, shipped model)

| Source | Pearson | 3-class accuracy | Binary accuracy |
|---|---:|---:|---:|
| Wikipedia (654 requests) | 0.704 | 62.2% | 89.6% |
| Stack Exchange (991 requests) | 0.421 | 51.1% | 74.2% |

### Test confusion matrix (shipped model; rows = human level, columns = predicted)

| | low | medium | high |
|---|---:|---:|---:|
| low | 352 | 125 | 72 |
| medium | 149 | 226 | 173 |
| high | 75 | 138 | 335 |

## Why 3-class accuracy stops in the mid-50s

The labels are noisy. From the five annotator scores, the reliability of the averaged label is about 0.83 (Wikipedia) and
0.75 (Stack Exchange). A simulation with those values puts the best achievable 3-class tertile accuracy at roughly 75% and
71%, and a single human annotator agrees with the other four on the tertile only 55% and 49% of the time. The "medium" band
is where most errors fall. Binary polite-versus-impolite accuracy is the more meaningful headline for this corpus.

## Predict

```bash
python3 Src/source/model/politeness/predict_politeness_v2.py "Could you please help me with this issue?"
python3 Src/source/model/politeness/score_message_csv_v2.py input.csv output.csv --text-column body
```

Sanity checks from the shipped model:

- `Would you mind helping me with this, please?` -> high (`1.1635`)
- `Hi team, thanks for the update. Could you send me the report by Friday when you get a chance?` -> high (`1.1744`)
- `Why would you even do that? This makes no sense.` -> low (`-1.3689`)
- `Fix this immediately.` -> medium (`0.1372`), with a short-input warning

## Known limitations

- Bare commands such as `Fix this immediately.` are scored medium, not low. The corpus contains requests phrased as
  questions and very few imperatives, so the model has little evidence about them.
- Stack Exchange-style technical comments are scored much less reliably than Wikipedia-style messages.
- Training data is English requests from Wikipedia and Stack Exchange, collected around 2011. Workplace email is out of domain
  and has not been evaluated.
- Levels are relative to this corpus. No calibrated uncertainty and no rewrite generation.
- The teacher started from the RoBERTa-base weights bundled with spaCy `en_core_web_trf`, because that was the pretrained
  model reachable from the training machine.

## Files

- `models/politeness_nn_iteration2/politeness_cnn.npz`, `vocab.json`, `metadata.json`: the shipped model.
- `models/politeness_nn_iteration2/evaluation.json`: full metrics for all four models.
- `models/politeness_nn_iteration2/test_predictions.csv`: held-out predictions (shipped model and teacher).
- `models/politeness_nn_iteration2/teacher_pseudo_labels.csv.gz`: the 179,607 teacher-scored requests.
- `Src/source/model/politeness/politeness_v2.py`, `predict_politeness_v2.py`, `score_message_csv_v2.py`: NumPy-only inference.
- `Src/source/model/politeness/iteration2_training/`: the scripts that produced the model.

## Next steps

1. Agree whether the product reports three levels or polite versus impolite.
2. Hand-label a small set of workplace messages to measure performance on the real target domain.
3. Add imperatives and curt workplace messages to that set, since the corpus under-represents them.
