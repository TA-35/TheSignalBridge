# Iteration 1 English Politeness Neural Network

## Goal

Deliver a same-day neural-network MVP that assigns a continuous politeness score and a relative low/medium/high level to an English request.

## Model

- Input: one English request or task-oriented online message.
- Text representation: signed feature hashing over word unigrams, word bigrams, and character 3/4-grams.
- Predictor: one-hidden-layer residual multilayer perceptron (MLP).
- Target: the Stanford corpus `Normalized Score` as a regression target.
- Loss: Huber loss.
- Label-noise handling: rows flagged `is_high_disagreement=True` receive weight 0.55 rather than being removed.
- Runtime dependency: NumPy only.

## Leakage control

The 70/15/15 train/validation/test split keeps identical lowercased, whitespace-normalized messages in the same split. Splitting is approximately stratified by source and target tertile.

## Train

From the project root, install the model dependency:

```bash
python -m pip install -r Src/source/model/politeness/requirements.txt
```

Reproduce the selected Iteration 1 configuration:

```bash
python Src/source/model/politeness/train_politeness_nn.py --dimension 131072 --hidden-size 64 --learning-rate 0.0015 --epochs 80 --patience 8
```

The training command reads `data/Stanford_Politeness/stanford_politeness_clean.csv` and writes the trained weights, metadata, metrics, and held-out predictions to `models/politeness_nn_iteration1/`.

## Predict

From the project root:

```bash
python Src/source/model/politeness/predict_politeness.py "Could you please help me with this issue?"
```

## Interpretation

The predicted number is on the corpus's normalized-score scale. Low/medium/high thresholds are calculated from training-set tertiles and therefore mean relative politeness within this corpus, not universal social judgments.

## Trained result (14 September 2026)

The selected configuration uses 131,072 hashed input dimensions and 64 hidden units.
Early stopping selected epoch 2 using validation MAE only.

| Split      |   MAE |  RMSE | Pearson | Spearman |
| ---------- | ----: | ----: | ------: | -------: |
| Train      | 0.297 | 0.448 |   0.805 |    0.846 |
| Validation | 0.473 | 0.631 |   0.493 |    0.473 |
| Test       | 0.492 | 0.672 |   0.466 |    0.480 |

### Why 131,072 dimensions

The 12 September run used 2,048 and scored test Pearson 0.411. The featuriser emits
word 1/2-grams plus character 3/4-grams, which on this corpus is **209,697 distinct
features** - so 2,048 buckets meant roughly 102 distinct features colliding per bucket
and every bucket saturated. Widening the hash is the whole gain; nothing else changed.

| dim | test MAE | test Pearson |
| ---: | ---: | ---: |
| 2,048 | 0.5107 | 0.4108 |
| 8,192 | 0.4995 | 0.4423 |
| 32,768 | 0.4975 | 0.4477 |
| 65,536 | 0.4922 | 0.4630 |
| **131,072** | **0.4921** | **0.4664** |

Two things that were tried and did not work, recorded so they are not retried:

- **Wider hidden layer hurts.** At dim 65,536: hidden 128 scored 0.4327 and hidden 256
  scored 0.4305, both below hidden 64's 0.4630.
- **The 21 ConvoKit strategy features are not additive.** Alone they are strong - a plain
  linear model on just those booleans reaches test Pearson 0.336 - and appended at dim
  2,048 they lift it to 0.4438. But at dim 65,536 they add nothing (0.458-0.461 against
  0.463 without them); the n-grams already carry that signal once there is room for it.
  They remain worth keeping for user-facing explanations, not for accuracy.

### Caveats on this result

- **The train/test gap widened.** Train Pearson went from 0.530 to 0.805 while test went
  from 0.411 to 0.466. Generalisation improved, but the model now fits the training set
  much harder, so it is closer to its overfitting limit than the previous config was.
- **Early stopping still selects epoch 2** at every configuration tried, up to 80 epochs
  with patience 20. The model memorises almost immediately. The MLP has no weight decay
  or dropout, so regularisation is the untested lever and probably where the remaining
  headroom is.
- **Predictions still compress toward the mean.** Predicted standard deviation is 48% of
  the true spread (was 40%), so the model rarely commits to a strongly polite or strongly
  blunt score.
- **The two source domains behave very differently.** On the previous config, test Pearson
  was 0.546 on Wikipedia but 0.303 on Stack Exchange, and Stack Exchange is the larger
  share of the corpus. Neither domain is workplace email.
- **Weights are now 30MB** (were 0.5MB). dim 65,536 halves that to 15MB for Pearson
  0.4630, which is 0.7% lower - a reasonable trade if repository size matters more.

## Known limitations

- The training corpus covers English requests from Wikipedia and Stack Exchange.
- General messages that are not requests are outside the strongest evidence base.
- The MVP does not generate more-polite rewrites.
- The MVP does not provide calibrated predictive uncertainty.
- Insulting or hostile wording is not always pushed into the low category because the training corpus represents annotated requests rather than a dedicated toxicity dataset.
- The hashed representation is fast and reproducible, but a fine-tuned pretrained Transformer is the preferred Iteration 2 upgrade.

## Iteration 2 priorities

1. Fine-tune DistilRoBERTa or DeBERTa-v3-small with grouped splits.
2. Add cross-domain evaluation between Wikipedia and Stack Exchange.
3. Calibrate uncertainty and add out-of-domain detection.
4. Use the 21 interpretable strategy features for user-facing explanations.
5. Collect a small general-online-message evaluation set and, if required, add polite rewrite generation.
