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
    date_text = str(data.get("date_text") or "").strip()
    printed = parse_date(date_text) if date_text else None   # day-first, as Malaysian receipts are printed
    if printed is not None:
        parsed_date = printed                                # trust the printed text over a mis-converted ISO date
    merchant = (data.get("merchant") or "").strip() or None
    out = finalize({"merchant": merchant, "date": parsed_date, "amount": amount})
    out["date_text"] = date_text
    return out


def finalize(f: dict) -> dict:
    """Fallback defaults so the user can complete the confirmation form."""
    return {
        "merchant": f.get("merchant") or "",
        "date": f.get("date") or date.today(),
        "amount": float(f["amount"]) if f.get("amount") is not None and f["amount"] >= 0 else 0.0,
        "complete": all(f.get(k) is not None and f.get(k) != "" for k in ("merchant", "date", "amount")),
    }


def validate_items(items, allowed):
    """Clean the item list returned by Gemini. `allowed` = category names the user may use.
    Items whose category is not allowed keep category=None (the caller falls back to the merchant guess)."""
    out = []
    lookup = {a.lower(): a for a in allowed}
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            amt = float(str(it.get("amount")).replace("RM", "").replace(",", "").strip())
        except (TypeError, ValueError):
            continue
        if amt <= 0:
            continue
        name = str(it.get("name") or "").strip()[:60]
        cat = lookup.get(str(it.get("category") or "").strip().lower())
        if not re.search(r"[A-Za-z]{3,}", name):      # only a code / number: any category would be a guess
            cat = None
        out.append({"name": name, "amount": round(amt, 2), "category": cat})
    return out


def suggest_split(items, total, fallback_category):
    """Group items by category and reconcile with the receipt total.
    Returns {"rows": [(category_name, amount), ...], "adjusted": bool} or None when not reliable
    (no items, or the items differ from the total by more than 25 %)."""
    if not items or not total or total <= 0:
        return None
    groups = {}
    for it in items:
        cat = it["category"] or fallback_category
        groups[cat] = round(groups.get(cat, 0.0) + it["amount"], 2)
    diff = round(total - round(sum(groups.values()), 2), 2)
    adjusted = False
    if abs(diff) > 0.005:                       # tax / rounding / discount not listed as items
        if abs(diff) / total > 0.25:
            return None
        biggest = max(groups, key=groups.get)
        groups[biggest] = round(groups[biggest] + diff, 2)
        adjusted = True
        if groups[biggest] <= 0:
            return None
    rows = sorted(groups.items(), key=lambda kv: -kv[1])
    return {"rows": [(c, round(a, 2)) for c, a in rows], "adjusted": adjusted}


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
