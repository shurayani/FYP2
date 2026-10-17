"""Data preprocessing: turns OCR output into three validated fields - merchant, date, total
(FR04, Section 5.6.4)."""
import re
from datetime import date, datetime

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
# Malay month abbreviations that differ from English
MONTHS.update({"mei": 5, "ogo": 8, "okt": 10, "dis": 12, "ogos": 8})

AMOUNT = r"(?:RM|MYR)?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})|[0-9]+\.[0-9]{1,2})"
TOTAL_KEYS = ["grand total", "total amount", "amount due", "total due", "jumlah besar", "jumlah",
              "total", "amount", "net total", "nett", "bayar", "cash", "tunai"]
SKIP_LINE = re.compile(r"(receipt|resit|invoice|tax|gst|sst|tel|phone|fax|www\.|http|reg|co\.?\s*no|"
                       r"^\W*$|^\d[\d\s\-/:.]*$)", re.I)


def _to_float(txt):
    try:
        return float(txt.replace(",", ""))
    except ValueError:
        return None


def parse_amount(text: str):
    """Pick the total: prefer lines containing TOTAL / JUMLAH keywords, else the largest RM amount."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for key in TOTAL_KEYS:
        for i, line in enumerate(lines):
            low = line.lower()
            if key in low and "sub" not in low.split(key)[0][-5:]:
                found = re.findall(AMOUNT, line, re.I)
                if not found and i + 1 < len(lines):          # amount printed on the next line
                    found = re.findall(AMOUNT, lines[i + 1], re.I)
                vals = [v for v in (_to_float(x) for x in found) if v is not None]
                if vals:
                    return max(vals)
    vals = [v for v in (_to_float(x) for x in re.findall(AMOUNT, text, re.I)) if v is not None]
    return max(vals) if vals else None


def parse_date(text: str):
    """Recognise DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD and DD MONTH YYYY."""
    for m in re.finditer(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b", text):
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            return date(y, mo, d)
        except ValueError:
            continue
    for m in re.finditer(r"\b(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})\b", text):
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
    for m in re.finditer(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{2,4})\b", text):
        mo = MONTHS.get(m.group(2).lower()[:4]) or MONTHS.get(m.group(2).lower()[:3])
        if mo:
            y = int(m.group(3))
            y = y + 2000 if y < 100 else y
            try:
                return date(y, mo, int(m.group(1)))
            except ValueError:
                continue
    return None


def parse_merchant(text: str):
    """Merchant = first meaningful non-empty line of the OCR text."""
    for line in text.splitlines():
        line = line.strip()
        if len(line) >= 3 and not SKIP_LINE.search(line):
            return re.sub(r"\s{2,}", " ", line)[:80]
    return None


def parse_fields(text: str) -> dict:
    """Parse raw OCR text (PaddleOCR path)."""
    return finalize({"merchant": parse_merchant(text or ""), "date": parse_date(text or ""),
                     "amount": parse_amount(text or "")})


def validate_structured(data: dict) -> dict:
    """Validate the structured response returned by Gemini (valid date, numeric amount)."""
    d = data.get("date")
    parsed_date = None
    if isinstance(d, str):
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
            try:
                parsed_date = datetime.strptime(d.strip(), fmt).date()
                break
            except ValueError:
                continue
    amount = data.get("amount")
    try:
        amount = float(str(amount).replace("RM", "").replace(",", "").strip())
    except (TypeError, ValueError):
        amount = None
    merchant = (data.get("merchant") or "").strip() or None
    return finalize({"merchant": merchant, "date": parsed_date, "amount": amount})


def finalize(f: dict) -> dict:
    """Fallback defaults so the user can complete the confirmation form."""
    return {
        "merchant": f.get("merchant") or "",
        "date": f.get("date") or date.today(),
        "amount": float(f["amount"]) if f.get("amount") is not None and f["amount"] >= 0 else 0.0,
        "complete": all(f.get(k) is not None and f.get(k) != "" for k in ("merchant", "date", "amount")),
    }
