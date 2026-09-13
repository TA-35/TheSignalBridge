import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neural_network import MLPClassifier
from sklearn.utils.class_weight import compute_sample_weight
from sklearn.metrics import classification_report, confusion_matrix, f1_score, precision_recall_curve

SPLIT = Path("data/staging/circa_model_split.parquet") #path of the saved data split
SEED = 2002 #keeps the model results consistent every time it runs


def load_splits():
    df = pd.read_parquet(SPLIT) #Loads the dataset with the saved train validation and test split
    print(f"loaded split: {len(df):,} rows") #Shows the total number of loaded rows
    parts = {name: df[df["split"] == name] for name in ["train", "val", "test"]} #Separates the data into train validation and test sets
    for name, part in parts.items(): #Goes through each part of the data
        print(f"  {name}: {len(part):,}") #shows how many rows are in each part
    return parts #returns all three parts


def report(name, y_true, y_pred):
    print("\n" + "=" * 60 + f"\n{name}\n" + "=" * 60) #prints the model name clearly
    print(classification_report(y_true, y_pred, target_names=["direct", "indirect"],
                                digits=3, zero_division=0)) #shows precision recall and F1 score for both classes
    print("confusion matrix [rows = actual, cols = predicted]:") #explains how the confusion matrix is arranged
    print(confusion_matrix(y_true, y_pred)) #shows the correct and incorrect predictions


def main():
    parts = load_splits() #Loads the saved data splits
    train, val, test = parts["train"], parts["val"], parts["test"] #Stores each split separately

    Xtr_text, ytr = train["answer-Y"].astype(str), train["label"].values #gets training text and labels
    Xvl_text, yvl = val["answer-Y"].astype(str), val["label"].values #gets validation text and labels
    Xte_text, yte = test["answer-Y"].astype(str), test["label"].values #gets test text and labels

    vec = TfidfVectorizer(min_df=2, ngram_range=(1, 2)) #creates TF IDF features using single words and pairs of words
    Xtr = vec.fit_transform(Xtr_text) #learns the vocabulary and converts training text into numbers
    Xvl = vec.transform(Xvl_text) #converts validation text using the same vocabulary
    Xte = vec.transform(Xte_text) #converts test text using the same vocabulary
    print(f"\nfeatures: {Xtr.shape[1]:,} TF-IDF terms") #shows how many text features were created

    clf = MLPClassifier(hidden_layer_sizes=(128,), activation="relu",
                        early_stopping=True, n_iter_no_change=8,
                        max_iter=200, random_state=SEED) #creates a small neural network with one hidden layer

    sample_weight = compute_sample_weight(class_weight="balanced", y=ytr) #calculates higher weights for the less common class
    clf.fit(Xtr, ytr) #trains the neural network using the training data

    val_scores = clf.predict_proba(Xvl)[:, 1] #gets the predicted probability of each validation answer being indirect
    prec, rec, thr = precision_recall_curve(yvl, val_scores) #calculates precision and recall for different thresholds
    f1s = 2 * prec * rec / (prec + rec + 1e-9) #calculates the F1 score for each threshold
    best = int(np.argmax(f1s)) #finds the position of the highest F1 score
    best_thr = thr[best] if best < len(thr) else 0.5 #uses the threshold that gives the best validation F1 score
    print(f"\nbest threshold on validation: {best_thr:.3f}  (val indirect F1 = {f1s[best]:.3f})") #shows the selected threshold and its F1 score

    report("Neural net (MLP) VALIDATION",
           yvl, (val_scores >= best_thr).astype(int)) #evaluates the model on validation data using the selected threshold

    test_scores = clf.predict_proba(Xte)[:, 1] #gets the probability of each test answer being indirect
    y_test_pred = (test_scores >= best_thr).astype(int) #converts the test probabilities into direct or indirect predictions
    report("Neural net (MLP) TEST (final)", yte, y_test_pred) #shows the final test results
    print(f"\nTEST indirect F1 = {f1_score(yte, y_test_pred):.3f}   (baseline was 0.570)") #compares the neural network F1 score with the baseline


if __name__ == "__main__":
    main() #runs the main function when this file is run directly