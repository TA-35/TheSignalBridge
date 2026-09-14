# enron_train.py
# finetunes distilbert on the labelled/balanced set.
# 3k rows trains in a few mins on gpu, dont need more than this

from pathlib import Path
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from datasets import Dataset
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score
from sklearn.utils.class_weight import compute_class_weight
from transformers import (
    AutoTokenizer, AutoModelForSequenceClassification,
    TrainingArguments, Trainer, EarlyStoppingCallback,
)

LABELED_FILE = Path("data/processed/enron_tone_labeled.csv")
MODEL_OUT = Path("models/enron_tone_distilbert")

LABELS = ["neutral", "casual", "terse"]  # formal merged into neutral
LABEL2ID = {l: i for i, l in enumerate(LABELS)}
ID2LABEL = {i: l for i, l in enumerate(LABELS)}

MODEL_NAME = "distilbert-base-uncased"
MAX_LEN = 256
BATCH_SIZE = 16
LR = 2e-5
EPOCHS = 3


def load_data():
    df = pd.read_csv(LABELED_FILE).dropna(subset=["body", "label"])
    df["label_id"] = df["label"].map(LABEL2ID)
    return train_test_split(df, test_size=0.15, random_state=42, stratify=df["label_id"])


def tokenize(df, tok):
    ds = Dataset.from_pandas(df[["body", "label_id"]].rename(columns={"label_id": "labels"}))
    return ds.map(lambda b: tok(b["body"], truncation=True, max_length=MAX_LEN, padding="max_length"), batched=True)


def compute_metrics(pred):
    logits, labels = pred
    preds = np.argmax(logits, axis=-1)
    return {"macro_f1": f1_score(labels, preds, average="macro")}


class WeightedTrainer(Trainer):
    """
    Regular Trainer just does plain cross-entropy, which means the model
    learns to always guess the majority class (neutral) on skewed data
    like this. Overriding compute_loss to weight rare classes (terse,
    formal) higher so mistakes on them actually cost something.
    """
    def __init__(self, *args, class_weights=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.class_weights = class_weights

    def compute_loss(self, model, inputs, return_outputs=False, **kwargs):
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        logits = outputs.logits
        loss_fct = nn.CrossEntropyLoss(weight=self.class_weights.to(logits.device))
        loss = loss_fct(logits.view(-1, len(LABELS)), labels.view(-1))
        return (loss, outputs) if return_outputs else loss


def main():
    if not LABELED_FILE.exists():
        print("run enron_label.py first")
        return

    train_df, val_df = load_data()
    print(f"train: {len(train_df)}, val: {len(val_df)}")

    # class weights - inverse frequency, so rare classes (terse, formal)
    # get penalized harder when the model gets them wrong
    weights = compute_class_weight(
        class_weight="balanced",
        classes=np.arange(len(LABELS)),
        y=train_df["label_id"].values,
    )
    class_weights = torch.tensor(weights, dtype=torch.float)
    print(f"class weights: {dict(zip(LABELS, weights.round(2)))}")

    tok = AutoTokenizer.from_pretrained(MODEL_NAME)
    train_ds = tokenize(train_df, tok)
    val_ds = tokenize(val_df, tok)

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=len(LABELS), id2label=ID2LABEL, label2id=LABEL2ID
    )

    args = TrainingArguments(
        output_dir="models/enron_tone_checkpoints",
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=LR,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        num_train_epochs=EPOCHS,
        load_best_model_at_end=True,
        metric_for_best_model="macro_f1",
        greater_is_better=True,
        logging_steps=10,
    )

    trainer = WeightedTrainer(
        model=model, args=args, train_dataset=train_ds, eval_dataset=val_ds,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=1)],
        class_weights=class_weights,
    )
    trainer.train()

    MODEL_OUT.mkdir(parents=True, exist_ok=True)
    trainer.save_model(str(MODEL_OUT))
    tok.save_pretrained(str(MODEL_OUT))
    print(f"saved to {MODEL_OUT}")


if __name__ == "__main__":
    main()