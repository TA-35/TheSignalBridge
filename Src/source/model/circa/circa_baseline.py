import pandas as pd
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.dummy import DummyClassifier
from sklearn.metrics import classification_report, confusion_matrix

IN = Path("data/staging/circa_clean.parquet") #Path of the cleaned Circa dataset.
SPLIT_OUT = Path("data/staging/circa_model_split.parquet")#Path where the final split data will be saved.
SEED = 2002 #Keeps the data split the same every time the code runs.
DIRECT = {"Yes", "No"} #Yes and No are treated as direct answers.


def load_and_label() -> pd.DataFrame:
    df = pd.read_parquet(IN) #Loads the cleaned Circa dataset
    print(f"loaded: {len(df):,} rows") #Shows how many rows were loaded

    df["label"] = (~df["goldstandard1"].isin(DIRECT)).astype(int) #Gives 0 to direct answers and 1 to indirect answers

    counts = df["label"].value_counts() #Counts how many direct and indirect answers we have
    pct = df["label"].value_counts(normalize=True).round(3) #Calculates the percentage of each class
    print(f"label balance -> direct(0): {counts.get(0,0):,} ({pct.get(0,0)})  "
          f"indirect(1): {counts.get(1,0):,} ({pct.get(1,0)})") #Prints the balance between direct and indirect answers
    return df #Returns the labelled dataset


def make_split(df: pd.DataFrame) -> pd.DataFrame:
    train, temp = train_test_split(df, test_size=0.30, stratify=df["label"], random_state=SEED) #Keeps 70 percent for training and 30 percent for validation and testing
    val, test = train_test_split(temp, test_size=0.50, stratify=temp["label"], random_state=SEED) #Divides the remaining data equally into validation and test data

    df["split"] = "train" #Starts by marking every row as training data
    df.loc[val.index, "split"] = "val"# Marks the validation rows
    df.loc[test.index, "split"] = "test" # Marks the test rows
    print(f"split -> train {len(train):,} | val {len(val):,} | test {len(test):,}") # Shows the number of rows in each split

    df.to_parquet(SPLIT_OUT, index=False) # Saves the exact split so it can be reused later
    print(f"saved split -> {SPLIT_OUT}") # Shows where the split dataset was saved
    return df # Returns the dataset with the split column added


def evaluate(name, y_true, y_pred):
    print("\n" + "=" * 60)#Prints a separator to make the results easier to read
    print(f"{name}") # Prints the name of the baseline being tested
    print("=" * 60) # Prints another separator
    print(classification_report(y_true, y_pred, target_names=["direct", "indirect"], digits=3)) #Shows precision recall and F1 score for both classes
    print("confusion matrix [rows = actual, cols = predicted]:") #Explains how to read the confusion matrix
    print(confusion_matrix(y_true, y_pred)) #Shows how many predictions were correct and incorrect


def main():
    df = load_and_label() #Loads the data and creates the binary labels
    df = make_split(df) #Splits the data into training validation and test sets

    train = df[df["split"] == "train"] #Selects only the training rows
    val = df[df["split"] == "val"] #Selects only the validation rows

    X_train, y_train = train["answer-Y"].astype(str), train["label"] #Gets the training text and its correct labels
    X_val, y_val = val["answer-Y"].astype(str), val["label"] #Gets the validation text and its correct labels

    dummy = DummyClassifier(strategy="most_frequent").fit(X_train, y_train) #Creates a simple model that always predicts the most common class
    evaluate("Baseline 1: majority class (always 'direct')", y_val, dummy.predict(X_val)) #Tests the simple baseline on validation data

    vectorizer = TfidfVectorizer(min_df=2) #Creates TF IDF features from words that appear at least twice
    Xtr = vectorizer.fit_transform(X_train) #Learns the vocabulary and converts training text into numbers
    Xvl = vectorizer.transform(X_val) #Converts validation text into numbers using the same vocabulary
    logreg = LogisticRegression(max_iter=1000, class_weight="balanced").fit(Xtr, y_train) #Trains logistic regression while giving both classes fair importance
    evaluate("Baseline 2: TF-IDF + logistic regression", y_val, logreg.predict(Xvl)) #Tests logistic regression on the validation data

    print("\nRecord the 'indirect' F1 from Baseline 2. That is the number the "
          "neural network has to beat.") #Reminds us which baseline score the neural network should improve


if __name__ == "__main__":
    main() #Runs the main function when this file is executed directly