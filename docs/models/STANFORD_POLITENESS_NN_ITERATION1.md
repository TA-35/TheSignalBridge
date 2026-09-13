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
python -m pip install -r Src/source/model/stanford_politeness/requirements.txt
```

Reproduce the selected Iteration 1 configuration:

```bash
python Src/source/model/stanford_politeness/train_politeness_nn.py --dimension 2048 --hidden-size 64 --learning-rate 0.0015 --epochs 30 --patience 6
```

The training command reads `data/Stanford_Politeness/stanford_politeness_clean.csv` and writes the trained weights, metadata, metrics, and held-out predictions to `models/politeness_nn_iteration1/`.

## Predict

From the project root:

```bash
python Src/source/model/stanford_politeness/predict_politeness.py "Could you please help me with this issue?"
```

## Interpretation

The predicted number is on the corpus's normalized-score scale. Low/medium/high thresholds are calculated from training-set tertiles and therefore mean relative politeness within this corpus, not universal social judgments.

## Trained result (12 September 2026)

The selected configuration uses 2,048 hashed input dimensions and 64 hidden units. Early stopping selected epoch 2 using validation MAE only.

| Split      |   MAE |  RMSE | Pearson | Spearman |
| ---------- | ----: | ----: | ------: | -------: |
| Train      | 0.458 | 0.625 |   0.530 |    0.536 |
| Validation | 0.481 | 0.648 |   0.450 |    0.441 |
| Test       | 0.511 | 0.694 |   0.411 |    0.423 |

The held-out test result shows useful but moderate predictive signal. It is appropriate for an Iteration 1 proof of concept, not a production claim.

Sanity-check examples from the trained model:

- `Fix this immediately.` → low (`-0.2090`), with a short-input warning.
- `Would you mind helping me with this, please?` → high (`0.4722`).
- `Could you please help me understand this problem? Thank you.` → high (`0.7609`).

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
