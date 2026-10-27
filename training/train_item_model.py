"""Train the ITEM-level classifier (TF-IDF unigram+bigram + Multinomial Naive Bayes, Laplace alpha = 1.0).

    python training/train_item_model.py

Input : training/receipt_items_dataset.csv   (columns: item_name, category, group)
Output: data/item_model.pkl and data/item_vectorizer.pkl

The printed F1-score uses a split that keeps near-identical item names together, but similar items still
appear on both sides, so it is OPTIMISTIC. Only real receipt items can give a valid evaluation."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.naive_bayes import MultinomialNB

from utils.config import ITEM_DATASET_PATH, ITEM_MODEL_PATH, ITEM_VECTORIZER_PATH


def _base_key(name: str) -> str:
    """Items that differ only by size / quantity / word order share the same key."""
    return " ".join(sorted(w for w in re.findall(r"[a-z]+", name) if len(w) > 2))


def train(verbose=True, seed=42):
    df = pd.read_csv(ITEM_DATASET_PATH).dropna(subset=["item_name", "category"])
    df["item_name"] = df["item_name"].astype(str).str.lower().str.strip()
    df = df.drop_duplicates("item_name").reset_index(drop=True)
    groups = df["item_name"].map(_base_key)
    tr, te = next(GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=seed).split(df, df["category"], groups))
    vec = TfidfVectorizer(ngram_range=(1, 2), lowercase=True, sublinear_tf=True)
    clf = MultinomialNB(alpha=1.0).fit(vec.fit_transform(df["item_name"].iloc[tr]), df["category"].iloc[tr])
    pred = clf.predict(vec.transform(df["item_name"].iloc[te]))
    f1 = f1_score(df["category"].iloc[te], pred, average="weighted")
    if verbose:
        print(f"{len(df)} items, {df['category'].nunique()} categories")
        print(classification_report(df["category"].iloc[te], pred, digits=3))
        print(f"Weighted F1-score (optimistic, see note in the file header): {f1:.3f}")
    vec_all = TfidfVectorizer(ngram_range=(1, 2), lowercase=True, sublinear_tf=True)
    clf_all = MultinomialNB(alpha=1.0).fit(vec_all.fit_transform(df["item_name"]), df["category"])
    joblib.dump(clf_all, ITEM_MODEL_PATH)
    joblib.dump(vec_all, ITEM_VECTORIZER_PATH)
    if verbose:
        print(f"Saved {ITEM_MODEL_PATH.name} and {ITEM_VECTORIZER_PATH.name}")
    return f1


if __name__ == "__main__":
    train()
