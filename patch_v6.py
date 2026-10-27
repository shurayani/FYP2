"""One-time patch #6 (Option B): Gemini reads the ITEMS on the receipt and suggests the category split.
  * online + Gemini : items are read, grouped by category and pre-filled as a split (you review/edit it)
  * offline / PaddleOCR : unchanged (category from the merchant name, manual split as in patch #5)
Items are only used to make the suggestion - they are NOT stored in the database.
Requires patch #5 first.   Run once from the project folder:   python patch_v6.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    s = p.read_text(encoding="utf-8")
    s = fn(s)
    p.write_text(s, encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found (did you run patch #5 first?): " + old[:70]
    return s.replace(old, new, 1)


# ============================================================ utils/gemini_helper.py
def f_gemini(s):
    if "items" in s and "Choose each item's category" in s:
        return s
    a = s.index("def extract_receipt_fields")
    b = s.index("def generate_insights")
    new = '''def extract_receipt_fields(jpeg_bytes: bytes, categories=None) -> dict:
    """Send the (resized, compressed) receipt image; get merchant / date / total AND the purchased items,
    each with a category chosen from `categories`, back as JSON."""
    cats = ", ".join(f'"{c}"' for c in (categories or []))
    prompt = ("You are reading a Malaysian retail receipt. Return ONLY a JSON object with keys: "
              '"merchant" (store name, string), "date" (YYYY-MM-DD), "amount" (grand total paid in MYR, number), '
              '"items" (array of purchased line items, each {"name": string, "amount": number (line total in MYR), '
              '"category": string}). '
              + (f"Choose each item's category from exactly this list: [{cats}]. " if cats else "")
              + "Choose the category by what the ITEM is, not by the type of shop (e.g. bread bought at a petrol "
                "station is food/groceries, not transport). If nothing fits perfectly use the closest category. "
                "Do not list tax, rounding, discounts, payment lines or totals as items. "
                "Use null (or an empty items array) for anything you cannot read.")
    parts = [{"text": prompt},
             {"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(jpeg_bytes).decode()}}]
    text = _call(parts, json_mode=True)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        data = json.loads(text)
    except ValueError:
        raise ParseError("Gemini returned invalid JSON")
    if not isinstance(data, dict):
        raise ParseError("Gemini returned unexpected JSON")
    return data


'''
    return s[:a] + new + s[b:]


edit("utils/gemini_helper.py", f_gemini)


# ============================================================ src/preprocessor.py
def f_pre(s):
    if "def suggest_split" in s:
        return s
    return s + '''

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
        out.append({"name": str(it.get("name") or "").strip()[:60], "amount": round(amt, 2),
                    "category": lookup.get(str(it.get("category") or "").strip().lower())})
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
'''


edit("src/preprocessor.py", f_pre)


# ============================================================ src/ocr_module.py
def f_ocr(s):
    if "categories=None" in s:
        return s
    s = swap(s, "def extract_receipt(image_bytes: bytes, prefer_offline: bool = False) -> dict:",
             "def extract_receipt(image_bytes: bytes, prefer_offline: bool = False, categories=None) -> dict:")
    s = swap(s, "data = gemini_helper.extract_receipt_fields(to_jpeg_bytes(img))",
             "data = gemini_helper.extract_receipt_fields(to_jpeg_bytes(img), categories)")
    s = swap(s, 'fields.update(engine="gemini", raw_text=str(data), seconds=round(time.time() - t0, 2), note="")',
             'fields.update(engine="gemini", raw_text=str(data), seconds=round(time.time() - t0, 2), note="",\n'
             '                          items=preprocessor.validate_items(data.get("items"), categories or []))')
    s = swap(s, 'fields.update(engine="paddleocr", raw_text=text, seconds=round(time.time() - t0, 2), note=note)',
             'fields.update(engine="paddleocr", raw_text=text, seconds=round(time.time() - t0, 2), note=note, items=[])')
    return s


edit("src/ocr_module.py", f_ocr)


# ============================================================ utils/i18n.py
def f_i18n(s):
    if "Gemini read the items" in s:
        return s
    return s + '''

MS.update({
    "Gemini read the items on this receipt and suggests the categories below. Please review them.":
        "Gemini membaca barang pada resit ini dan mencadangkan kategori di bawah. Sila semak.",
    "Items read from the receipt": "Barang yang dibaca dari resit",
    "Item": "Barang",
    "Category suggested from the receipt items.": "Kategori dicadangkan daripada barang pada resit.",
    "The suggested split was adjusted for tax, rounding or discounts.":
        "Pecahan yang dicadangkan dilaraskan untuk cukai, pembundaran atau diskaun.",
})
'''


edit("utils/i18n.py", f_i18n)


# ============================================================ pages/2_Receipts.py
def f_page(s):
    if "suggestion" in s:
        return s
    s = swap(s, "from src import analytics, classifier, db_manager as db, ocr_module, receipt_manager",
             "from src import analytics, classifier, db_manager as db, ocr_module, preprocessor, receipt_manager")

    # split_section: optional pre-filled rows + pre-ticked checkbox
    a = s.index("def split_section(key, total, default_label):")
    b = s.index("# ------------------------------------------------------------------------- OCR upload")
    s = s[:a] + '''def split_section(key, total, default_label, initial_rows=None):
    """Optional 'split across several categories' editor.
    initial_rows = suggested [(category_label, amount), ...] (e.g. from Gemini); the box is then pre-ticked.
    Returns (rows, ok): rows = [(category_label, amount), ...] or None when splitting is off;
    ok = True when the rows add up exactly to the total."""
    st.session_state.setdefault(f"{key}_split", bool(initial_rows and len(initial_rows) > 1))
    if not st.checkbox(t("Split across several categories"), key=f"{key}_split"):
        return None, True
    st.caption(t("Set the total first, then edit the rows. Add a row by clicking the empty row at the bottom of the table."))
    if initial_rows:
        base = pd.DataFrame({"category": [c for c, _ in initial_rows], "amount": [a for _, a in initial_rows]})
    else:
        base = pd.DataFrame({"category": [default_label], "amount": [round(float(total), 2)]})
    edited = st.data_editor(
        base, num_rows="dynamic", hide_index=True, width="stretch", key=f"{key}_ed_{round(float(total), 2)}",
        column_config={
            "category": st.column_config.SelectboxColumn(t("Category"), options=labels, required=True),
            "amount": st.column_config.NumberColumn(t("Amount (RM)"), min_value=0.01, step=0.10, format="%.2f", required=True),
        })
    rows = [(r["category"], round(float(r["amount"]), 2)) for _, r in edited.iterrows()
            if pd.notna(r["category"]) and pd.notna(r["amount"]) and float(r["amount"]) > 0]
    allocated = round(sum(a for _, a in rows), 2)
    remaining = round(float(total) - allocated, 2)
    ok = bool(rows) and abs(remaining) < 0.005
    if ok:
        st.success(t("Allocated {a} of {tot}.", a=ui.money(allocated), tot=ui.money(total)))
    else:
        st.warning(t("Allocated {a} of {tot}. Remaining: {r}", a=ui.money(allocated), tot=ui.money(total), r=ui.money(remaining)))
    return rows, ok


''' + s[b:]

    # extraction: pass the user's category names to Gemini, build the suggestion
    s = swap(s, "                        res = ocr_module.extract_receipt(data)\n",
             "                        mine = db.get_categories(uid)\n"
             "                        res = ocr_module.extract_receipt(data, categories=[c[\"category_name\"] for c in mine])\n")
    s = swap(s, '                        res["confidence"] = conf\n',
             '                        res["confidence"] = conf\n'
             '                        res["suggestion"] = preprocessor.suggest_split(res.get("items"), res["amount"], cat_name)\n'
             '                        sug = res["suggestion"]\n'
             '                        if sug:                                   # category decided from the ITEMS\n'
             '                            name_to_id = {c["category_name"]: c["id"] for c in mine}\n'
             '                            res["category_id"] = name_to_id.get(sug["rows"][0][0], res["category_id"])\n'
             '                            res["confidence"] = 1.0\n')

    # confirmation form: explanation + items table + pre-filled split rows
    s = swap(s, '        st.caption(t("Please check and correct the values before saving."))\n',
             '        sug = res.get("suggestion")\n'
             '        if sug:\n'
             '            st.info(t("Gemini read the items on this receipt and suggests the categories below. Please review them."))\n'
             '            if sug["adjusted"]:\n'
             '                st.caption(t("The suggested split was adjusted for tax, rounding or discounts."))\n'
             '            with st.expander(t("Items read from the receipt")):\n'
             '                st.dataframe(pd.DataFrame({t("Item"): [i["name"] for i in res["items"]],\n'
             '                                           t("Amount (RM)"): [i["amount"] for i in res["items"]],\n'
             '                                           t("Category"): [ui.cat_label(i["category"]) if i["category"] else "-" for i in res["items"]]}),\n'
             '                             hide_index=True, width="stretch")\n'
             '        st.caption(t("Please check and correct the values before saving."))\n')
    s = swap(s, '        rows, split_ok = split_section(f"cf_{k}", amount, default_label)\n',
             '        initial = None\n'
             '        if sug and abs(amount - float(res["amount"])) < 0.005:      # only while the total is unchanged\n'
             '            initial = [(ui.cat_label(c), a) for c, a in sug["rows"] if ui.cat_label(c) in cats]\n'
             '        rows, split_ok = split_section(f"cf_{k}", amount, default_label, initial)\n')
    return s


edit("pages/2_Receipts.py", f_page)

# ============================================================ longer Gemini timeout (items take longer to read)
for name in (".env", ".env.example"):
    p = ROOT / name
    if p.exists():
        txt = p.read_text(encoding="utf-8")
        if "GEMINI_TIMEOUT=8" in txt:
            p.write_text(txt.replace("GEMINI_TIMEOUT=8", "GEMINI_TIMEOUT=20"), encoding="utf-8")
            print(name, ": GEMINI_TIMEOUT set to 20")
p = ROOT / "utils" / "config.py"
txt = p.read_text(encoding="utf-8")
p.write_text(txt.replace('os.getenv("GEMINI_TIMEOUT", "8")', 'os.getenv("GEMINI_TIMEOUT", "20")'), encoding="utf-8")

print("Done. Restart Streamlit.")