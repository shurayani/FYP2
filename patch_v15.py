"""One-time patch #15: clear messages about WHY Gemini was not used for a receipt.
  * Gemini errors now carry Google's own explanation, e.g.
        Gemini (gemini-3.8-flash) could not be used: HTTP 404 - models/... is not found
        Gemini (gemini-3.8-flash) could not be used: daily quota used up (HTTP 429)
        Gemini (gemini-3.8-flash) could not be used: took longer than 20 s
  * laptop: when IPECS switches to PaddleOCR, the blue note under 'Extracted with: PaddleOCR' says why
  * cloud (no PaddleOCR): the red error says why Gemini failed and suggests the Manual Data Form
Run once from the project folder:   python patch_v15.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


# ============================================================ utils/gemini_helper.py: keep Google's error text
def f_gemini(s):
    if "def _google_message" in s:
        return s
    s = swap(s, "def _call(parts, json_mode=False, timeout=None):", '''def _google_message(r) -> str:
    """Google's own error explanation from a failed response (never contains the API key)."""
    try:
        msg = r.json().get("error", {}).get("message", "")
    except ValueError:
        msg = ""
    return " ".join(str(msg).split())[:220]


def _call(parts, json_mode=False, timeout=None):''')
    s = swap(s, '''    except (requests.ConnectionError, requests.Timeout) as e:
        raise NetworkError(str(e))
    if r.status_code in (429, 403):
        raise QuotaError(f"HTTP {r.status_code}")
    if r.status_code != 200:
        raise NetworkError(f"HTTP {r.status_code}")
''', '''    except requests.Timeout:
        raise NetworkError(f"took longer than {timeout or GEMINI_TIMEOUT:g} s")
    except requests.ConnectionError:
        raise NetworkError("could not connect to the Gemini server")
    if r.status_code == 200:
        pass
    elif r.status_code == 429:
        raise QuotaError("quota used up or too many requests (HTTP 429) - " + _google_message(r))
    elif r.status_code in (400, 401, 403):
        raise QuotaError(f"API key or permission problem (HTTP {r.status_code}) - " + _google_message(r))
    elif r.status_code == 404:
        raise NetworkError(f"model '{GEMINI_MODEL}' was not found (HTTP 404) - check GEMINI_MODEL. " + _google_message(r))
    else:
        raise NetworkError(f"HTTP {r.status_code} - " + _google_message(r))
''')
    return s


edit("utils/gemini_helper.py", f_gemini)
print("gemini_helper.py ok")


# ============================================================ src/ocr_module.py: say why, on both laptop and cloud
def f_ocr(s):
    if "could not be used:" in s:
        return s
    s = swap(s, 'note = f"Gemini unavailable ({e}); switched to PaddleOCR."',
             'note = f"Gemini ({gemini_helper.GEMINI_MODEL}) could not be used: {str(e).rstrip(\' .-\')}. Switched to PaddleOCR."')
    s = swap(s, 'note = "No Gemini API key configured; using PaddleOCR."',
             'note = "No Gemini API key configured (GEMINI_API_KEY). Using PaddleOCR."')
    s = swap(s, 'note = "Offline; using PaddleOCR."',
             'note = "No internet connection was detected. Using PaddleOCR."')
    s = swap(s, '''        raise RuntimeError("PaddleOCR is not installed, and Gemini is not available. "
                           "Install paddleocr/paddlepaddle (see README) or enter the transaction manually.")''',
             '''        reason = note.replace(" Switched to PaddleOCR.", "").replace(" Using PaddleOCR.", "")
        raise RuntimeError(f"{reason} PaddleOCR (offline OCR) is not installed on this computer/server, so the "
                           "receipt could not be read. Please use the Manual Data Form, or try again later.")''')
    return s


edit("src/ocr_module.py", f_ocr)
print("ocr_module.py ok")
print("Done. Commit and push to GitHub (the cloud updates itself), then scan a receipt and read the message.")