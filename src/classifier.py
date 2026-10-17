"""Expense categorisation: TF-IDF (unigram + bigram) + Multinomial Naive Bayes (Laplace smoothing)
(FR05, Section 5.6.5). The fitted artefacts are loaded from data/*.pkl at import time; if they are
missing or were saved by an incompatible scikit-learn version they are re-trained automatically."""
import joblib

from utils.config import MODEL_PATH, VECTORIZER_PATH

_model = None
_vectorizer = None


def _load():
    global _model, _vectorizer
    try:
        _model = joblib.load(MODEL_PATH)
        _vectorizer = joblib.load(VECTORIZER_PATH)
    except Exception:
        from training.train_model import train          # re-train from training/receipt_dataset.csv
        train(verbose=False)
        _model = joblib.load(MODEL_PATH)
        _vectorizer = joblib.load(VECTORIZER_PATH)


_load()


def predict_category_name(merchant: str) -> str:
    """Return the predicted system-category name for the merchant text."""
    text = (merchant or "").strip().lower()
    if not text:
        return "Food and Beverage"
    return str(_model.predict(_vectorizer.transform([text]))[0])


def predict_with_confidence(merchant: str):
    text = (merchant or "").strip().lower()
    if not text:
        return "Food and Beverage", 0.0
    proba = _model.predict_proba(_vectorizer.transform([text]))[0]
    i = int(proba.argmax())
    return str(_model.classes_[i]), float(proba[i])


def predict_category_id(merchant: str) -> str:
    from src.db_manager import category_uuid
    return category_uuid(predict_category_name(merchant))
