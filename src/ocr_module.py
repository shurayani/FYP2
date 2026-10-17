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

from src import preprocessor
from utils import gemini_helper
from utils.gemini_helper import NetworkError, ParseError, QuotaError

_paddle = None


# ---------------------------------------------------------------- connectivity
def is_online(timeout: float = 2.0) -> bool:
    for host, port in (("1.1.1.1", 53), ("8.8.8.8", 53)):
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


def paddle_ocr(img) -> str:
    """Run local PaddleOCR on the preprocessed image and return the text, one line per box."""
    engine = _get_paddle()
    rgb = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img
    lines = []
    if hasattr(engine, "predict"):                         # PaddleOCR 3.x
        for page in engine.predict(rgb) or []:
            texts = page["rec_texts"] if "rec_texts" in page else []
            lines.extend(str(x) for x in texts)
    else:                                                  # PaddleOCR 2.x: [[box, (text, score)], ...]
        for page in engine.ocr(rgb, cls=True) or []:
            for item in page or []:
                try:
                    lines.append(item[1][0])
                except (IndexError, TypeError):
                    pass
    return "\n".join(lines)


# ---------------------------------------------------------------- engine selector
def extract_receipt(image_bytes: bytes, prefer_offline: bool = False) -> dict:
    """Returns {merchant, date, amount, complete, engine, raw_text, seconds, note}.
    Raises RuntimeError only if BOTH engines are unavailable."""
    t0 = time.time()
    img = decode_image(image_bytes)
    note = ""

    if not prefer_offline and gemini_helper.is_configured() and is_online():
        try:
            data = gemini_helper.extract_receipt_fields(to_jpeg_bytes(img))
            fields = preprocessor.validate_structured(data)
            if data.get("amount") is None and data.get("merchant") is None:
                raise ParseError("empty Gemini response")
            fields.update(engine="gemini", raw_text=str(data), seconds=round(time.time() - t0, 2), note="")
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
    text = paddle_ocr(processed)
    fields = preprocessor.parse_fields(text)
    fields.update(engine="paddleocr", raw_text=text, seconds=round(time.time() - t0, 2), note=note)
    return fields
