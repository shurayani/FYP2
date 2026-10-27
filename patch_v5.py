"""One-time patch #5: split ONE receipt across SEVERAL categories (one transaction per category).
  * OCR confirmation form and Manual form get a 'Split across several categories' option
  * the receipt gallery shows how many transactions a receipt is linked to
Includes the low-confidence warning of patch #4, so it is safe to run whether or not you ran patch #4.
Run once from the project folder:   python patch_v5.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ---- utils/config.py (low-confidence threshold, same as patch #4)
p = ROOT / "utils" / "config.py"
s = p.read_text(encoding="utf-8")
if "LOW_CONFIDENCE_THRESHOLD" not in s:
    s += ("LOW_CONFIDENCE_THRESHOLD = 0.40     # below this the user is asked to double-check the category\n"
          "                                    # (re-tune after retraining: Naive Bayes probabilities depend on the dataset)\n")
    p.write_text(s, encoding="utf-8")
    print("config.py patched")

# ---- utils/i18n.py (new BM strings)
p = ROOT / "utils" / "i18n.py"
s = p.read_text(encoding="utf-8")
if "Low confidence" not in s:
    s += '''

MS.update({
    "Low confidence: the suggested category may be wrong (it is based on the merchant name only). Please check it.":
        "Keyakinan rendah: kategori yang dicadangkan mungkin salah (ia berdasarkan nama kedai sahaja). Sila semak.",
    "Low confidence: please check the category in the Transactions page.":
        "Keyakinan rendah: sila semak kategori di halaman Transaksi.",
})
'''
if "Split across several categories" not in s:
    s += '''

MS.update({
    "Split across several categories": "Pecahkan kepada beberapa kategori",
    "Set the total first, then edit the rows. Add a row by clicking the empty row at the bottom of the table.":
        "Tetapkan jumlah dahulu, kemudian edit baris. Tambah baris dengan mengklik baris kosong di bawah jadual.",
    "Allocated {a} of {tot}.": "Diperuntukkan {a} daripada {tot}.",
    "Allocated {a} of {tot}. Remaining: {r}": "Diperuntukkan {a} daripada {tot}. Baki: {r}",
    "The split amounts must add up exactly to the total.": "Jumlah pecahan mesti sama tepat dengan jumlah keseluruhan.",
    "{n} transactions saved.": "{n} transaksi disimpan.",
    "Linked transactions": "Transaksi berkaitan",
})
'''
p.write_text(s, encoding="utf-8")
print("i18n.py ok")

# ---- src/db_manager.py: one row per receipt even when it has several transactions
p = ROOT / "src" / "db_manager.py"
s = p.read_text(encoding="utf-8")
if "GROUP BY r.id" not in s:
    a = s.index("def get_receipts(user_id):")
    b = s.index("def get_receipt(receipt_id):")
    s = s[:a] + '''def get_receipts(user_id):
    with get_conn() as c:
        return _rows(c.execute("""
            SELECT r.*, COUNT(t.id) AS tx_count, COALESCE(SUM(t.amount), 0) AS tx_amount,
                   MIN(t.merchant) AS tx_merchant
            FROM receipts r LEFT JOIN transactions t ON t.receipt_id=r.id AND t.is_deleted=0
            WHERE r.user_id=? AND r.is_deleted=0 GROUP BY r.id ORDER BY r.upload_date DESC""", (user_id,)))


''' + s[b:]
    p.write_text(s, encoding="utf-8")
    print("db_manager.py patched")

# ---- pages/2_Receipts.py (full replacement)
PAGE = r'''"""Module 2: Receipt Management - upload / camera, hybrid OCR, confirmation form, manual entry, gallery.
A receipt can be saved as ONE transaction or split across SEVERAL categories (one transaction per category)."""
import uuid
from datetime import date

import pandas as pd
import streamlit as st

from src import analytics, classifier, db_manager as db, ocr_module, receipt_manager
from utils import ui
from utils.config import LOW_CONFIDENCE_THRESHOLD
from utils.i18n import t

user = ui.require_login()
uid = user["id"]
st.title(f"{t('Receipt & Transaction Entry')}")

cats = ui.category_map(uid)                       # {label: id}
labels = list(cats.keys())
id_to_label = {v: k for k, v in cats.items()}

tab_ocr, tab_manual, tab_gallery = st.tabs([t("OCR Receipt Upload"), t("Manual Data Form"), t("Receipt Gallery")])


def _category_index(cat_id):
    return labels.index(id_to_label[cat_id]) if cat_id in id_to_label else 0


def split_section(key, total, default_label):
    """Optional 'split across several categories' editor.
    Returns (rows, ok): rows = [(category_label, amount), ...] or None when splitting is off;
    ok = True when the rows add up exactly to the total."""
    if not st.checkbox(t("Split across several categories"), key=f"{key}_split"):
        return None, True
    st.caption(t("Set the total first, then edit the rows. Add a row by clicking the empty row at the bottom of the table."))
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


# ------------------------------------------------------------------------- OCR upload
with tab_ocr:
    online = ui.online_status()
    st.caption(t("Gemini AI is used when online; PaddleOCR is used automatically when offline or if Gemini fails.")
               + "  " + ((":green[●] " + t("Online")) if online else (":red[●] " + t("Offline"))))
    source = st.radio(t("Image source"), [t("Upload file"), t("Take a photo")], horizontal=True)
    img_file = (st.file_uploader(t("Receipt image (JPEG or PNG, up to 10 MB)"), type=["jpg", "jpeg", "png"])
                if source == t("Upload file") else st.camera_input(t("Take a photo of the receipt")))

    if img_file is not None:
        data = img_file.getvalue()
        fname = getattr(img_file, "name", "camera.jpg") or "camera.jpg"
        ok, msg = receipt_manager.validate_upload(fname, len(data))
        if not ok:
            st.error(t(msg))
        else:
            st.image(data, caption=fname, width=320)
            if st.button(t("Extract transaction details"), type="primary"):
                with st.spinner(t("Reading receipt...")):
                    try:
                        res = ocr_module.extract_receipt(data)
                        cat_name, conf = classifier.predict_with_confidence(res["merchant"])
                        res["category_id"] = db.category_uuid(cat_name)
                        res["confidence"] = conf
                        st.session_state["ocr_result"] = {**res, "file_name": fname, "data": data,
                                                          "uid": uuid.uuid4().hex[:8]}
                    except Exception as e:
                        st.session_state.pop("ocr_result", None)
                        st.error(f"{t('Extraction failed')}: {e}")

    res = st.session_state.get("ocr_result")
    if res:
        k = res.get("uid", "0")
        st.divider()
        engine_label = "Gemini AI" if res["engine"] == "gemini" else "PaddleOCR"
        st.success(f"{t('Extracted with')}: **{engine_label}** ({res['seconds']} s)")
        if res.get("note"):
            st.info(res["note"])
        if not res.get("complete"):
            st.warning(t("Some fields could not be read reliably. Please complete them below."))
        if res.get("confidence", 1.0) < LOW_CONFIDENCE_THRESHOLD:
            st.warning(t("Low confidence: the suggested category may be wrong (it is based on the merchant name only). Please check it."))
        st.caption(t("Please check and correct the values before saving."))

        merchant = st.text_input(t("Merchant"), value=res["merchant"], key=f"cf_m_{k}")
        c1, c2 = st.columns(2)
        tx_date = c1.date_input(t("Date"), value=res["date"], key=f"cf_d_{k}")
        amount = c2.number_input(t("Total amount (RM)"), min_value=0.0, value=float(res["amount"]), step=0.10,
                                 format="%.2f", key=f"cf_a_{k}")
        default_label = id_to_label.get(res["category_id"], labels[0])
        rows, split_ok = split_section(f"cf_{k}", amount, default_label)
        if rows is None:
            cat_label = st.selectbox(t("Category"), labels, index=_category_index(res["category_id"]), key=f"cf_c_{k}")
        c3, c4 = st.columns(2)
        save = c3.button(t("Confirm and save"), type="primary", key=f"cf_save_{k}")
        cancel = c4.button(t("Discard"), key=f"cf_cancel_{k}")

        if save:
            if not merchant.strip() or amount <= 0:
                st.error(t("Merchant and a positive amount are required."))
            elif rows is not None and not split_ok:
                st.error(t("The split amounts must add up exactly to the total."))
            else:
                rel = receipt_manager.save_image(uid, res["file_name"], res["data"])
                rid = db.add_receipt(uid, rel, res["file_name"], res["raw_text"], res["engine"])
                parts = rows if rows is not None else [(cat_label, amount)]
                for label, amt in parts:
                    db.add_transaction(uid, merchant, tx_date, amt, cats[label], is_manual=False, receipt_id=rid)
                analytics.detect_anomalies(uid)
                st.session_state.pop("ocr_result", None)
                st.session_state["flash_ocr"] = (t("{n} transactions saved.", n=len(parts)) if len(parts) > 1
                                                 else t("Transaction saved."))
                st.rerun()
        if cancel:
            st.session_state.pop("ocr_result", None)
            st.rerun()
    elif st.session_state.get("flash_ocr"):
        st.success(st.session_state.pop("flash_ocr"))

# ------------------------------------------------------------------------- manual entry
with tab_manual:
    st.caption(t("Record a transaction without a receipt. Leave the category on Auto to let the classifier decide."))
    n = st.session_state.setdefault("manual_n", 0)          # bumping it clears the form after a save
    if st.session_state.get("manual_flash"):
        text, low = st.session_state.pop("manual_flash")
        st.success(text)
        if low:
            st.warning(t("Low confidence: please check the category in the Transactions page."))
    auto = t("Auto (classify automatically)")
    merchant = st.text_input(t("Merchant"), key=f"man_m_{n}")
    c1, c2 = st.columns(2)
    tx_date = c1.date_input(t("Date"), value=date.today(), key=f"man_d_{n}")
    amount = c2.number_input(t("Amount (RM)"), min_value=0.0, value=0.0, step=0.10, format="%.2f", key=f"man_a_{n}")
    guess = id_to_label.get(db.category_uuid(classifier.predict_category_name(merchant)), labels[0]) if merchant.strip() else labels[0]
    rows, split_ok = split_section(f"man_{n}", amount, guess)
    if rows is None:
        cat_choice = st.selectbox(t("Category"), [auto] + labels, key=f"man_c_{n}")
    go = st.button(t("Save transaction"), type="primary", key=f"man_save_{n}")
    if go:
        if not merchant.strip() or amount <= 0:
            st.error(t("Merchant and a positive amount are required."))
        elif rows is not None and not split_ok:
            st.error(t("The split amounts must add up exactly to the total."))
        else:
            low_conf = False
            if rows is not None:
                for label, amt in rows:
                    db.add_transaction(uid, merchant, tx_date, amt, cats[label], is_manual=True)
                text = t("{n} transactions saved.", n=len(rows)) if len(rows) > 1 else t("Transaction saved.")
            else:
                if cat_choice == auto:
                    cat_name, conf = classifier.predict_with_confidence(merchant)
                    cid, low_conf = db.category_uuid(cat_name), conf < LOW_CONFIDENCE_THRESHOLD
                else:
                    cid = cats[cat_choice]
                if cid not in id_to_label:                    # predicted category missing/deleted -> first available
                    cid = list(cats.values())[0]
                db.add_transaction(uid, merchant, tx_date, amount, cid, is_manual=True)
                text = f"{t('Transaction saved.')} {t('Category')}: {id_to_label[cid]}"
            analytics.detect_anomalies(uid)
            st.session_state["manual_flash"] = (text, low_conf)
            st.session_state["manual_n"] = n + 1
            st.rerun()

# ------------------------------------------------------------------------- gallery
with tab_gallery:
    receipts = db.get_receipts(uid)
    if not receipts:
        st.info(t("No receipts uploaded yet."))
    cols = st.columns(3)
    for i, r in enumerate(receipts):
        with cols[i % 3]:
            with st.container(border=True):
                img = receipt_manager.read_image_bytes(r["file_path"])
                try:
                    if not img:
                        raise ValueError("missing")
                    st.image(img, width="stretch")
                except Exception:                                # missing or corrupt image file
                    st.caption(t("Image file not found on this device."))
                st.caption(f"{t('Uploaded')}: {r['upload_date'][:10]} · {r['ocr_engine'] or '—'}")
                if r["tx_count"]:
                    label = t("Linked transaction") if r["tx_count"] == 1 else f"{t('Linked transactions')} ({r['tx_count']})"
                    st.caption(f"{label}: {r['tx_merchant']} · {ui.money(r['tx_amount'])}")
                with st.expander(t("Replace / delete")):
                    new_img = st.file_uploader(t("New image"), type=["jpg", "jpeg", "png"], key=f"rep_{r['id']}")
                    if new_img and st.button(t("Replace image"), key=f"repbtn_{r['id']}"):
                        d = new_img.getvalue()
                        ok, msg = receipt_manager.validate_upload(new_img.name, len(d))
                        if ok:
                            rel = receipt_manager.replace_image(uid, r["file_path"], new_img.name, d)
                            db.update_receipt(r["id"], uid, file_path=rel, original_filename=new_img.name)
                            st.rerun()
                        else:
                            st.error(t(msg))
                    if st.button(t("Delete receipt"), key=f"del_{r['id']}"):
                        receipt_manager.delete_image(r["file_path"])
                        db.delete_receipt(r["id"], uid)
                        st.rerun()
'''
(ROOT / "pages" / "2_Receipts.py").write_text(PAGE, encoding="utf-8")
print("2_Receipts.py replaced")
print("Done. Restart Streamlit.")