import numpy as np
import pandas as pd
from pathlib import Path
from sentence_transformers import SentenceTransformer
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import classification_report, confusion_matrix, f1_score, precision_recall_curve

SPLIT = Path("data/staging/circa_model_split.parquet") #Path of the saved data split
SEED = 2002 #Keeps the results consistent every time the code runs
MODEL_NAME = "all-MiniLM-L6-v2" #small and fast model used to understand the meaning of text


def load_splits():
    df = pd.read_parquet(SPLIT) #loads dataset with the saved train validation and test split
    print(f"loaded split: {len(df):,} rows") #shows total number of loaded rows
    return {name: df[df["split"] == name] for name in ["train", "val", "test"]} #separates and returns the three data parts


def build_text(part):
    q = part["question-X"].astype(str) #gets the question text from each row
    a = part["answer-Y"].astype(str) #gets the answer text from each row
    return ("Question: " + q + "  Answer: " + a).tolist() #combines the question and answer so the model can understand their meaning together


def report(name, y_true, y_pred):
    print("\n" + "=" * 60 + f"\n{name}\n" + "=" * 60) #prints the model name clearly
    print(classification_report(y_true, y_pred, target_names=["direct", "indirect"],
                                digits=3, zero_division=0)) #shows precision recall and F1 score for both classes
    print("confusion matrix [rows = actual, cols = predicted]:") #explains how the confusion matrix is arranged
    print(confusion_matrix(y_true, y_pred)) #shows the correct and incorrect predictions


def main():
    parts = load_splits() #load saved data splits
    train, val, test = parts["train"], parts["val"], parts["test"] #stores each data split separately

    print(f"loading embedder: {MODEL_NAME}") #shows which embedding model is being loaded
    embedder = SentenceTransformer(MODEL_NAME) #loads the model used to convert text into meaning based numbers

    print("embedding train / val / test") #shows that the text conversion process has started
    Xtr = embedder.encode(build_text(train), show_progress_bar=True, batch_size=64) #converts the training text into embeddings
    Xvl = embedder.encode(build_text(val), show_progress_bar=True, batch_size=64) #converts the validation text into embeddings
    Xte = embedder.encode(build_text(test), show_progress_bar=True, batch_size=64) #converts the test text into embeddings
    ytr, yvl, yte = train["label"].values, val["label"].values, test["label"].values #gets the correct labels for all three data splits
    print(f"embedding size: {Xtr.shape[1]} dimensions per sentence") #shows the size of each text embedding

    clf = MLPClassifier(hidden_layer_sizes=(128,), activation="relu",
                        early_stopping=True, n_iter_no_change=8,
                        max_iter=300, random_state=SEED) #creates a small neural network with one hidden layer
    clf.fit(Xtr, ytr) #trains the neural network using the training embeddings

    val_scores = clf.predict_proba(Xvl)[:, 1] #gets the probability of each validation answer being indirect
    prec, rec, thr = precision_recall_curve(yvl, val_scores) #calculates precision and recall at different thresholds
    f1s = 2 * prec * rec / (prec + rec + 1e-9) #calculates the F1 score for each threshold
    best = int(np.argmax(f1s)) #finds the position of the highest F1 score
    best_thr = thr[best] if best < len(thr) else 0.5 #selects the threshold with the best validation F1 score
    print(f"\nbest threshold on validation: {best_thr:.3f}  (val indirect F1 = {f1s[best]:.3f})") #shows the best threshold and validation F1 score

    report("Embeddings + MLP VALIDATION", yvl, (val_scores >= best_thr).astype(int)) #checks the model performance on validation data

    test_scores = clf.predict_proba(Xte)[:, 1] #gets the probability of each test answer being indirect
    y_test_pred = (test_scores >= best_thr).astype(int) #converts the probabilities into direct or indirect predictions
    report("Embeddings + MLP TEST (final)", yte, y_test_pred) #shows the final model performance on test data
    print(f"\nTEST indirect F1 = {f1_score(yte, y_test_pred):.3f}   "
          f"(TF-IDF was 0.610, baseline 0.570)") #compares the final F1 score with the previous models


if __name__ == "__main__":
    main() #runs the main function when this file is executed directly