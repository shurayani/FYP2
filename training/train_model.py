"""Train the TF-IDF + Multinomial Naive Bayes expense classifier (Section 5.6.5).

    python training/train_model.py

Evaluates on a stratified held-out test set against the 80 % weighted F1-score acceptance threshold
(NFR02 / Objective ii), then serialises data/nb_model.pkl and data/tfidf_vectorizer.pkl."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB

from utils.config import DATASET_PATH, MIN_F1_THRESHOLD, MODEL_PATH, VECTORIZER_PATH


def train(verbose=True, test_size=0.2, seed=42):
    df = pd.read_csv(DATASET_PATH).dropna()
    df["merchant"] = df["merchant"].astype(str).str.lower().str.strip()
    X_tr, X_te, y_tr, y_te = train_test_split(df["merchant"], df["category"], test_size=test_size,
                                              random_state=seed, stratify=df["category"])
    vec = TfidfVectorizer(ngram_range=(1, 2), lowercase=True, sublinear_tf=True)
    clf = MultinomialNB(alpha=1.0)                              # Laplace smoothing
    clf.fit(vec.fit_transform(X_tr), y_tr)
    pred = clf.predict(vec.transform(X_te))
    f1 = f1_score(y_te, pred, average="weighted")
    if verbose:
        print(classification_report(y_te, pred, digits=3))
        print(f"Weighted F1-score: {f1:.3f}  (threshold {MIN_F1_THRESHOLD:.2f}) ->",
              "PASS" if f1 >= MIN_F1_THRESHOLD else "FAIL")
    # final artefacts are trained on the full dataset
    vec_full = TfidfVectorizer(ngram_range=(1, 2), lowercase=True, sublinear_tf=True)
    clf_full = MultinomialNB(alpha=1.0).fit(vec_full.fit_transform(df["merchant"]), df["category"])
    joblib.dump(clf_full, MODEL_PATH)
    joblib.dump(vec_full, VECTORIZER_PATH)
    if verbose:
        print(f"Saved {MODEL_PATH.name} and {VECTORIZER_PATH.name}")
    return f1


if __name__ == "__main__":
    train()
