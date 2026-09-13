import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import classification_report, confusion_matrix, f1_score, precision_recall_curve

SPLIT = Path("data/staging/circa_model_split.parquet") #path of the saved train validation and test split
SEED = 2002 #keeps the results consistent every time the code runs


def load_splits():
    df = pd.read_parquet(SPLIT) #loads the saved dataset split
    print(f"loaded split: {len(df):,} rows") #shows the total number of rows
    return {name: df[df["split"] == name] for name in ["train", "val", "test"]} #separates and returns the train validation and test data


def build_text(part):
    q = part["question-X"].astype(str) #gets the question text from each row
    a = part["answer-Y"].astype(str) #gets the answer text from each row
    return "Q: " + q + " A: " + a #Combines the question and answer so the model can use both for prediction


def report(name, y_true, y_pred):
    print("\n" + f"\n{name}\n") #Prints the model name clearly
    print(classification_report(y_true, y_pred, target_names=["direct", "indirect"],
                                digits=3, zero_division=0)) #shows precision recall and F1 score for both classes
    print("confusion matrix [rows = actual, cols = predicted]:") #explains how the confusion matrix is arranged
    print(confusion_matrix(y_true, y_pred)) #shows the correct and incorrect predictions


def run_one(label, vectorizer, texts, labels):
    """Train + tune + evaluate one representation. Returns the test indirect F1."""
    Xtr_text, Xvl_text, Xte_text = texts #Gets the train validation and test text
    ytr, yvl, yte = labels #Gets the correct labels for all three data parts

    Xtr = vectorizer.fit_transform(Xtr_text) #Learns the text features from the training data and converts it into numbers
    Xvl = vectorizer.transform(Xvl_text) #Converts the validation text using the same learned features
    Xte = vectorizer.transform(Xte_text)#Converts the test text using the same learned features
    print(f"\n {label} — {Xtr.shape[1]:,} features") #Shows the model type and number of created features

    clf = MLPClassifier(hidden_layer_sizes=(128,), activation="relu",
                        early_stopping=True, n_iter_no_change=8,
                        max_iter=200, random_state=SEED) #Creates a small neural network with one hidden layer
    clf.fit(Xtr, ytr) #Trains the neural network using the training data

    val_scores = clf.predict_proba(Xvl)[:, 1] #Gets the probability of each validation answer being indirect
    prec, rec, thr = precision_recall_curve(yvl, val_scores) #Calculates precision and recall for different thresholds
    f1s = 2 * prec * rec / (prec + rec + 1e-9) #Calculates the F1 score for each threshold
    best = int(np.argmax(f1s)) #Finds the position of the highest F1 score
    best_thr = thr[best] if best < len(thr) else 0.5 #Selects the threshold with the best validation F1 score
    print(f"best threshold on validation: {best_thr:.3f}  (val indirect F1 = {f1s[best]:.3f})") #Shows the selected threshold and its F1 score

    report(f"{label} — VALIDATION", yvl, (val_scores >= best_thr).astype(int)) #checks the model performance on validation data

    test_scores = clf.predict_proba(Xte)[:, 1] #gets the probability of each test answer being indirect
    y_test_pred = (test_scores >= best_thr).astype(int) #Converts the test probabilities into direct or indirect predictions
    report(f"{label} — TEST (final)", yte, y_test_pred) #Shows the final test results
    f1 = f1_score(yte, y_test_pred) #Calculates the indirect F1 score on the test data
    print(f"==> {label} TEST indirect F1 = {f1:.3f}") #Shows the final F1 score for this text representation
    return f1 #Returns the test F1 score so it can be compared later


def main():
    parts = load_splits() #loads the saved data splits
    train, val, test = parts["train"], parts["val"], parts["test"] #stores each data split separately
    texts = (build_text(train), build_text(val), build_text(test)) #Builds combined question and answer text for all data parts
    labels = (train["label"].values, val["label"].values, test["label"].values) #Gets the correct labels for all data parts

    results = {} #Stores the final F1 score from each text representation

    results["word 1-2 grams"] = run_one(
        "WORD unigrams+bigrams",
        TfidfVectorizer(min_df=2, ngram_range=(1, 2), sublinear_tf=True),
        texts, labels) #Tests TF IDF using single words and pairs of words

    results["char 2-5 grams"] = run_one(
        "CHAR 2-5 grams",
        TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=2, sublinear_tf=True),
        texts, labels) #Tests TF IDF using small groups of characters

    print("SUMMARY (test indirect F1) - beat 0.610 to improve on circa_nn.py")  #Shows the score that the new model needs to beat
    for k, v in results.items(): #Goes through the result of each representation
        print(f"  {k:<18} {v:.3f}") #Prints the final F1 score for each representation
    print("(previous: TF-IDF answer-only 0.610, baseline 0.570)") #Shows the previous scores for comparison


if __name__ == "__main__":
    main() #runs the main function when this file is executed directly