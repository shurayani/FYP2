"""Item-level categorisation (TF-IDF + Multinomial Naive Bayes trained on training/receipt_items_dataset.csv).

The model is optional: if the CSV / model files are missing every function simply does nothing."""
import re

import joblib

from utils.config import ITEM_DATASET_PATH, ITEM_MIN_CONF, ITEM_MODEL_PATH, ITEM_VECTORIZER_PATH

_model = None
_vec = None
_failed = False


def _ensure() -> bool:
    global _model, _vec, _failed
    if _model is not None:
        return True
    if _failed:
        return False
    try:
        try:
            _model = joblib.load(ITEM_MODEL_PATH)
            _vec = joblib.load(ITEM_VECTORIZER_PATH)
        except Exception:                                   # missing / incompatible files -> (re)train
            if not ITEM_DATASET_PATH.exists():
                raise FileNotFoundError(str(ITEM_DATASET_PATH))
            from training.train_item_model import train
            train(verbose=False)
            _model = joblib.load(ITEM_MODEL_PATH)
            _vec = joblib.load(ITEM_VECTORIZER_PATH)
        return True
    except Exception:
        _failed = True
        _model = _vec = None
        return False


def available() -> bool:
    return _ensure()


def predict(name: str, allowed=None):
    """Return (category, confidence). `allowed` = category names the user has; the model is then restricted to those."""
    if not _ensure() or not (name or "").strip():
        return None, 0.0
    proba = _model.predict_proba(_vec.transform([name.lower().strip()]))[0]
    classes = list(_model.classes_)
    idx = [i for i, c in enumerate(classes) if allowed is None or c in allowed]
    if not idx:
        return None, 0.0
    best = max(idx, key=lambda i: proba[i])
    return str(classes[best]), float(proba[best])             # absolute probability: no inflation when classes are excluded


def classify_items(items, allowed=None):
    """Add the model's opinion to every item (dicts with name / amount / category).
    * category missing  -> filled by the model when it is confident         (model_filled = True)
    * category present but the model disagrees confidently -> kept, model_category is stored for the UI
    Names that are only a code/number are never classified."""
    if not items or not _ensure():
        return items
    for it in items:
        if not re.search(r"[A-Za-z]{3,}", it.get("name") or ""):
            continue
        cat, conf = predict(it["name"], allowed)
        if cat is None or conf < ITEM_MIN_CONF:
            continue
        it["model_category"], it["model_conf"] = cat, round(conf, 3)
        if not it.get("category"):
            it["category"] = cat
            it["model_filled"] = True
    return items
