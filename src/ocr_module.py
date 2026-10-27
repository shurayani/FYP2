"""Hybrid OCR pipeline (Module 2, FR03/FR15, Section 5.6.3).

1. OpenCV preprocessing: grayscale -> adaptive threshold -> deskew (used for PaddleOCR).
2. Engine selector: online -> Gemini (resized/compressed image, structured JSON);
   offline OR Gemini failure (network, timeout, quota, unparsable) -> PaddleOCR (local).
3. Returns the extracted fields + the name of the engine that produced them.
"""
import os
import socket
import time

import cv2
import numpy as np

from src import item_classifier, preprocessor
from utils import gemini_helper
from utils.gemini_helper import NetworkError, ParseError, QuotaError

_paddle = None


# ---------------------------------------------------------------- connectivity
def is_online(timeout: float = 2.0) -> bool:
    for host, port in (("1.1.1.1", 53), ("8.8.8.8", 53), ("generativelanguage.googleapis.com", 443)):
        try:
            socket.create_connection((host, port), timeout=timeout).close()
            return True
        except OSError:
            continue
    return False


# ---------------------------------------------------------------- OpenCV pipeline
def decode_image(data: bytes):
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not read the image file.")
    return img


def _deskew(binary):
    """Estimate the text skew angle from the foreground pixels and rotate to correct it."""
    inv = cv2.bitwise_not(binary)
    coords = np.column_stack(np.where(inv > 0))
    if len(coords) < 50:
        return binary
    angle = cv2.minAreaRect(coords.astype(np.float32))[-1]
    angle = -(90 + angle) if angle < -45 else -angle
    if angle > 45 or angle < -45 or abs(angle) < 0.3:
        return binary
    h, w = binary.shape[:2]
    m = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    rotated = cv2.warpAffine(binary, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return cv2.threshold(rotated, 127, 255, cv2.THRESH_BINARY)[1]      # keep the image strictly binary


def preprocess(img):
    """Grayscale -> adaptive thresholding -> deskewing."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
    return _deskew(binary)


def to_jpeg_bytes(img, max_side: int = 1600, quality: int = 80) -> bytes:
    """Resize + compress to reduce Gemini usage."""
    h, w = img.shape[:2]
    scale = max_side / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes()


# ---------------------------------------------------------------- PaddleOCR (offline engine)
def _get_paddle():
    """Create the PaddleOCR engine once (lazy: it is heavy and only needed offline).
    Works with PaddleOCR 2.7.x and 3.x. oneDNN is disabled to avoid a Windows CPU crash."""
    global _paddle
    if _paddle is None:
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        os.environ["FLAGS_use_mkldnn"] = "0"
        from paddleocr import PaddleOCR
        try:      # PaddleOCR 3.x
            _paddle = PaddleOCR(lang="en", use_doc_orientation_classify=False,
                                use_doc_unwarping=False, use_textline_orientation=False,
                                enable_mkldnn=False)
        except (TypeError, ValueError):   # PaddleOCR 2.x
            _paddle = PaddleOCR(use_angle_cls=True, lang="en", show_log=False, enable_mkldnn=False)
    return _paddle


def paddle_available() -> bool:
    try:
        import importlib.util
        return importlib.util.find_spec("paddleocr") is not None
    except Exception:
        return False


def _boxes_3x(page, n):
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


# ---------------------------------------------------------------- engine selector
def extract_receipt(image_bytes: bytes, prefer_offline: bool = False, categories=None) -> dict:
    """Returns {merchant, date, amount, complete, engine, raw_text, seconds, note}.
    Raises RuntimeError only if BOTH engines are unavailable."""
    t0 = time.time()
    img = decode_image(image_bytes)
    note = ""

    if not prefer_offline and gemini_helper.is_configured() and is_online():
        try:
            data = gemini_helper.extract_receipt_fields(to_jpeg_bytes(img), categories)
            fields = preprocessor.validate_structured(data)
            if data.get("amount") is None and data.get("merchant") is None:
                raise ParseError("empty Gemini response")
            fields.update(engine="gemini", raw_text=str(data), seconds=round(time.time() - t0, 2), note="",
                          items=item_classifier.classify_items(
                              preprocessor.validate_items(data.get("items"), categories or []), categories))
            return fields
        except (NetworkError, QuotaError, ParseError) as e:     # -> fall back to PaddleOCR
            note = f"Gemini unavailable ({e}); switched to PaddleOCR."
    elif not prefer_offline and not gemini_helper.is_configured():
        note = "No Gemini API key configured; using PaddleOCR."
    elif not prefer_offline:
        note = "Offline; using PaddleOCR."

    if not paddle_available():
        raise RuntimeError("PaddleOCR is not installed, and Gemini is not available. "
                           "Install paddleocr/paddlepaddle (see README) or enter the transaction manually.")
    processed = preprocess(img)
    text, rows_text = paddle_ocr_rows(processed)
    fields = preprocessor.parse_fields(text)
    try:                                              # offline line items: best effort, never blocks the receipt
        items = preprocessor.parse_items(rows_text or text, fields["amount"])
        items = item_classifier.classify_items(items, categories)
    except Exception:
        items = []
    fields.update(engine="paddleocr", raw_text=text, seconds=round(time.time() - t0, 2), note=note, items=items)
    return fields
