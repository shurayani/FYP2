"""One-time patch #9: connect the item dataset (training/receipt_items_dataset.csv) to the app.
  * trains an item-level Naive Bayes model (TF-IDF + Multinomial NB) from the CSV
  * ONLINE : Gemini reads the items; the model fills items Gemini could not categorise and shows
             'Model suggests X' where it disagrees with Gemini
  * OFFLINE: best-effort - items are parsed from the PaddleOCR text and categorised by the model
             (only shown when they add up to the receipt total, otherwise the app falls back to merchant-only)
First copy receipt_items_dataset.csv into the training folder.   Requires patches #5-#8.
Run once from the project folder:   python patch_v9.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found (did you run patches #5-#8 first?): " + old[:70]
    return s.replace(old, new, 1)


# ============================================================ utils/config.py
def f_config(s):
    if "ITEM_MIN_CONF" in s:
        return s
    return s + ('ITEM_DATASET_PATH = TRAINING_DIR / "receipt_items_dataset.csv"\n'
                'ITEM_MODEL_PATH = DATA_DIR / "item_model.pkl"\n'
                'ITEM_VECTORIZER_PATH = DATA_DIR / "item_vectorizer.pkl"\n'
                'ITEM_MIN_CONF = 0.40                # below this the item model stays silent\n')


edit("utils/config.py", f_config)

# ============================================================ training/train_item_model.py (new)
(ROOT / "training" / "train_item_model.py").write_text(r'''"""Train the ITEM-level classifier (TF-IDF unigram+bigram + Multinomial Naive Bayes, Laplace alpha = 1.0).

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
''', encoding="utf-8")

# ============================================================ src/item_classifier.py (new)
(ROOT / "src" / "item_classifier.py").write_text(r'''"""Item-level categorisation (TF-IDF + Multinomial Naive Bayes trained on training/receipt_items_dataset.csv).

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
''', encoding="utf-8")


# ============================================================ src/preprocessor.py: parse line items from OCR text
def f_pre(s):
    if "def parse_items" in s:
        return s
    return s + r'''

# ---------------------------------------------------------------- offline line items (best effort)
_ITEM_SKIP = re.compile(
    r"(total|jumlah|cash|tunai|change|baki|balance|tax|gst|sst|service|rounding|pembundaran|discount|diskaun|"
    r"\bdisc\b|voucher|card|debit|credit|visa|master|approval|auth|rrn|terminal|merchant|batch|receipt|invoice|"
    r"item\(s\)|qty|quantity|\btel\b|phone|www|thank|terima kasih|points?|member|ewallet|\bqr\b|amount|\bdue\b|"
    r"paid|bayar|nett|operator|cashier|\bedc\b|date|time|tarikh|host|trace|signature|contactless)", re.I)


def _split_tail(line):
    """Peel qty / 'x' / unit price / line total off the END of a line -> (name, [prices])."""
    toks = line.split()
    prices = []
    while toks:
        tok = toks[-1]
        if re.fullmatch(r"(?:RM)?\d{1,5}\.\d{2}", tok, re.I):
            prices.insert(0, float(re.sub(r"(?i)rm", "", tok)))
            toks.pop()
        elif prices and re.fullmatch(r"[xX@]|\d{1,3}[xX]?|RM", tok, re.I):
            toks.pop()
        else:
            break
    return " ".join(toks), prices


def parse_items(text, total):
    """Best-effort line items from OCR text. Returns [{'name','amount','category': None}] or [] when the
    items do not add up to the receipt total (within 25 %), so a bad parse never reaches the user."""
    if not text or not total or total <= 0:
        return []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    found = []
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if _ITEM_SKIP.search(line):
            continue
        name, prices = _split_tail(line)
        letters = len(re.findall(r"[A-Za-z]", name))
        if prices and letters >= 3:
            found.append((name, prices[-1]))
        elif not prices and letters >= 3 and i < len(lines) and not _ITEM_SKIP.search(lines[i]):
            code, p2 = _split_tail(lines[i])             # name on one line, 'CODE qty x price total' on the next
            if p2 and len(re.findall(r"[A-Za-z]", code)) < 3:
                found.append((name, p2[-1]))
                i += 1

    def close(items):
        s = sum(a for _, a in items)
        return bool(items) and abs(total - s) / total <= 0.25

    if len(found) > 1 and not close(found):             # drop lines that just echo the total (e.g. 'EDC RM 19.90')
        found = [(n, a) for n, a in found if abs(a - total) > 0.005]
    if not close(found):
        return []
    out = []
    for n, a in found:
        n = re.sub(r"^\d+\s*[xX]?\s+", "", n).strip()[:60]
        if len(re.findall(r"[A-Za-z]", n)) >= 3 and a > 0:
            out.append({"name": n, "amount": round(a, 2), "category": None})
    return out if close([(x["name"], x["amount"]) for x in out]) else []
'''


edit("src/preprocessor.py", f_pre)


# ============================================================ src/ocr_module.py
def f_ocr(s):
    if "paddle_ocr_rows" in s:
        return s
    s = swap(s, "from src import preprocessor\n", "from src import item_classifier, preprocessor\n")
    a = s.index("def paddle_ocr(img) -> str:")
    b = s.index("# ---------------------------------------------------------------- engine selector")
    new = r'''def _boxes_3x(page, n):
    """Bounding boxes (x1, y1, x2, y2) of the recognised texts in a PaddleOCR 3.x result, or None."""
    try:
        if "rec_boxes" in page:
            arr = np.asarray(page["rec_boxes"], dtype=float)
            if arr.ndim == 2 and arr.shape[1] == 4 and len(arr) == n:
                return [tuple(a) for a in arr]
        if "rec_polys" in page:
            polys = [np.asarray(p, dtype=float) for p in page["rec_polys"]]
            if len(polys) == n:
                return [(p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()) for p in polys]
    except Exception:
        pass
    return None


def _group_rows(entries):
    """entries = [(text, x1, y1, x2, y2)] -> text with one line per VISUAL row (boxes on the same row are
    joined left to right), so an item name and its price end up on the same line."""
    if not entries:
        return ""
    heights = sorted(max(e[4] - e[2], 1.0) for e in entries)
    tol = 0.6 * heights[len(heights) // 2]
    ents = sorted(entries, key=lambda e: (e[2] + e[4]) / 2)
    rows, centres = [], []
    for e in ents:
        yc = (e[2] + e[4]) / 2
        if rows and abs(yc - sum(centres[-1]) / len(centres[-1])) <= tol:
            rows[-1].append(e)
            centres[-1].append(yc)
        else:
            rows.append([e])
            centres.append([yc])
    return "\n".join("  ".join(x[0] for x in sorted(r, key=lambda e: e[1])) for r in rows)


def paddle_ocr_rows(img):
    """Run local PaddleOCR once. Returns (text, rows_text): text = one line per detected box (used for
    merchant / date / total), rows_text = boxes merged per visual row (used for line items)."""
    engine = _get_paddle()
    rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img
    lines, entries = [], []
    if hasattr(engine, "predict"):                         # PaddleOCR 3.x
        for page in engine.predict(rgb) or []:
            texts = [str(x) for x in (page["rec_texts"] if "rec_texts" in page else [])]
            boxes = _boxes_3x(page, len(texts))
            for k, tx in enumerate(texts):
                lines.append(tx)
                if boxes:
                    entries.append((tx,) + tuple(boxes[k]))
    else:                                                  # PaddleOCR 2.x: [[box, (text, score)], ...]
        for page in engine.ocr(rgb, cls=True) or []:
            for item in page or []:
                try:
                    tx = item[1][0]
                    pts = np.asarray(item[0], dtype=float)
                    lines.append(tx)
                    entries.append((tx, pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()))
                except Exception:
                    pass
    try:
        rows = _group_rows(entries) if len(entries) == len(lines) else ""
    except Exception:
        rows = ""
    return "\n".join(lines), rows


def paddle_ocr(img) -> str:
    """Run local PaddleOCR on the preprocessed image and return the text, one line per box."""
    return paddle_ocr_rows(img)[0]


'''
    s = s[:a] + new + s[b:]
    # Gemini path: add the model's opinion to the items
    s = swap(s, 'items=preprocessor.validate_items(data.get("items"), categories or []))',
             'items=item_classifier.classify_items(\n'
             '                              preprocessor.validate_items(data.get("items"), categories or []), categories))')
    # PaddleOCR path: best-effort offline items
    s = swap(s, "    text = paddle_ocr(processed)\n    fields = preprocessor.parse_fields(text)\n"
                '    fields.update(engine="paddleocr", raw_text=text, seconds=round(time.time() - t0, 2), note=note, items=[])\n',
             "    text, rows_text = paddle_ocr_rows(processed)\n    fields = preprocessor.parse_fields(text)\n"
             "    try:                                              # offline line items: best effort, never blocks the receipt\n"
             '        items = preprocessor.parse_items(rows_text or text, fields["amount"])\n'
             "        items = item_classifier.classify_items(items, categories)\n"
             "    except Exception:\n"
             "        items = []\n"
             '    fields.update(engine="paddleocr", raw_text=text, seconds=round(time.time() - t0, 2), note=note, items=items)\n')
    return s


edit("src/ocr_module.py", f_ocr)


# ============================================================ pages/2_Receipts.py
def f_page(s):
    if "Set by the model" in s:
        return s
    s = swap(s, '            st.info(t("Gemini read the items on this receipt. Each item has its own category - please review them."))\n',
             '            if res.get("engine") == "gemini":\n'
             '                st.info(t("Gemini read the items on this receipt. Each item has its own category - please review them."))\n'
             '            else:\n'
             '                st.warning(t("The items were read offline from the OCR text. This is less reliable - please check every row."))\n')
    s = swap(s, "    unknown = sum(1 for i in items if not (i[\"category\"] and ui.cat_label(i[\"category\"]) in cats))\n",
             "    def _note(i):\n"
             "        if i.get(\"model_filled\"):\n"
             "            return t(\"Set by the model\")\n"
             "        mc = i.get(\"model_category\")\n"
             "        if mc and i.get(\"category\") and mc != i[\"category\"]:\n"
             "            return t(\"Model suggests {c}\", c=ui.cat_label(mc))\n"
             "        return \"\"\n"
             "    base[\"note\"] = [_note(i) for i in items]\n"
             "    unknown = sum(1 for i in items if not (i[\"category\"] and ui.cat_label(i[\"category\"]) in cats))\n")
    s = swap(s, '            "category": st.column_config.SelectboxColumn(t("Category"), options=labels, required=True),\n        })\n    item_rows = [',
             '            "category": st.column_config.SelectboxColumn(t("Category"), options=labels, required=True),\n'
             '            "note": st.column_config.TextColumn(t("Note"), disabled=True),\n        })\n    item_rows = [')
    return s


edit("pages/2_Receipts.py", f_page)


# ============================================================ utils/i18n.py
def f_i18n(s):
    if "Set by the model" in s:
        return s
    return s + """

MS.update({
    "The items were read offline from the OCR text. This is less reliable - please check every row.":
        "Barang dibaca secara luar talian daripada teks OCR. Ini kurang tepat - sila semak setiap baris.",
    "Set by the model": "Ditetapkan oleh model",
    "Model suggests {c}": "Model cadangkan {c}",
    "Note": "Catatan",
})
"""


edit("utils/i18n.py", f_i18n)

# ============================================================ train now (if the CSV is in place)
csv = ROOT / "training" / "receipt_items_dataset.csv"
if csv.exists():
    import subprocess
    import sys
    print("training the item model ...")
    subprocess.run([sys.executable, str(ROOT / "training" / "train_item_model.py")], cwd=str(ROOT), check=False)
else:
    print("NOTE: training/receipt_items_dataset.csv not found. Copy the file there, then run: python training/train_item_model.py")
print("Done. Restart Streamlit.")