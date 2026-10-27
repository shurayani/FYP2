"""Module 2: Receipt Management - upload / camera, hybrid OCR, confirmation form, manual entry, gallery.
A receipt can be saved as ONE transaction or split across SEVERAL categories (one transaction per category)."""
import uuid
from datetime import date

import pandas as pd
import streamlit as st

from src import analytics, classifier, db_manager as db, ocr_module, preprocessor, receipt_manager
from utils import ui
from utils.config import LOW_CONFIDENCE_THRESHOLD
from utils.i18n import t

user = ui.require_login()
uid = user["id"]
st.title(f"{t('Receipt & Transaction Entry')}")
ui.budget_banner(uid)

cats = ui.category_map(uid)                       # {label: id}
labels = list(cats.keys())
id_to_label = {v: k for k, v in cats.items()}

tab_ocr, tab_manual, tab_gallery = st.tabs([t("OCR Receipt Upload"), t("Manual Data Form"), t("Receipt Gallery")])


def _category_index(cat_id):
    return labels.index(id_to_label[cat_id]) if cat_id in id_to_label else 0


def split_section(key, total, default_label, initial_rows=None):
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


def _spread(groups, diff):
    """Spread `diff` (RM, may be negative) over the category totals in proportion to their size, in whole sen."""
    total = sum(groups.values())
    cents = round(diff * 100)
    alloc = {k: round(cents * v / total) for k, v in groups.items()}
    alloc[max(groups, key=groups.get)] += cents - sum(alloc.values())
    return {k: round(groups[k] + alloc[k] / 100, 2) for k in groups}


def item_editor(key, items, total, default_label):
    """Item-level editor: one row per purchased item, each with its own category.
    Returns (item_rows, groups, ok): item_rows = [(name, amount, category_label)], groups = [(category_label, amount)]
    (items grouped by category; a small tax/rounding/discount difference is added to the biggest group)."""
    base = pd.DataFrame({
        "item": [i["name"] or "-" for i in items],
        "amount": [i["amount"] for i in items],
        "category": [ui.cat_label(i["category"]) if i["category"] and ui.cat_label(i["category"]) in cats else default_label
                     for i in items]})
    def _note(i):
        if i.get("model_filled"):
            return t("Set by the model")
        mc = i.get("model_category")
        if mc and i.get("category") and mc != i["category"]:
            return t("Model suggests {c}", c=ui.cat_label(mc))
        return ""
    base["note"] = [_note(i) for i in items]
    unknown = sum(1 for i in items if not (i["category"] and ui.cat_label(i["category"]) in cats))
    if unknown:
        st.warning(t("{n} item(s) could not be categorised because the name is unreadable or only a code. They use the shop's category - please check them.", n=unknown))
    edited = st.data_editor(
        base, num_rows="dynamic", hide_index=True, width="stretch", key=f"{key}_items",
        column_config={
            "item": st.column_config.TextColumn(t("Item"), required=True),
            "amount": st.column_config.NumberColumn(t("Amount (RM)"), min_value=0.01, step=0.10, format="%.2f", required=True),
            "category": st.column_config.SelectboxColumn(t("Category"), options=labels, required=True),
            "note": st.column_config.TextColumn(t("Note"), disabled=True),
        })
    item_rows = [(str(r["item"]).strip(), round(float(r["amount"]), 2), r["category"]) for _, r in edited.iterrows()
                 if pd.notna(r["item"]) and pd.notna(r["amount"]) and pd.notna(r["category"])
                 and float(r["amount"]) > 0 and str(r["item"]).strip()]
    if not item_rows:
        st.warning(t("Add at least one item."))
        return [], [], False
    groups = {}
    for _, amt, label in item_rows:
        groups[label] = round(groups.get(label, 0.0) + amt, 2)
    items_sum = round(sum(groups.values()), 2)
    diff = round(float(total) - items_sum, 2)          # < 0: discount / voucher,  > 0: delivery, service charge, tax
    ok = True
    if abs(diff) > 0.005:
        if total > 0 and abs(diff) <= 0.7 * max(items_sum, float(total)):
            groups = _spread(groups, diff)
            ok = all(v > 0 for v in groups.values())
            if abs(diff) <= 0.10:
                st.caption(t("Rounding of {d} is spread across the categories.", d=ui.money(abs(diff))))
            elif diff < 0:
                st.info(t("Discount or voucher of {d} detected: the items add up to {s} but you paid {tot}. "
                          "It is spread across the categories in proportion to their amounts.",
                          d=ui.money(abs(diff)), s=ui.money(items_sum), tot=ui.money(total)))
            else:
                st.info(t("Extra charges of {d} (delivery, service charge, tax) detected: the items add up to {s} but you paid {tot}. "
                          "They are spread across the categories in proportion to their amounts.",
                          d=ui.money(diff), s=ui.money(items_sum), tot=ui.money(total)))
        else:
            ok = False
            st.warning(t("The items add up to {s} but the receipt total is {tot}. Fix the items or the total.",
                         s=ui.money(items_sum), tot=ui.money(total)))
    if ok:
        st.markdown(f"**{t('Transactions that will be saved')}**")
        st.dataframe(pd.DataFrame({t("Category"): list(groups.keys()), "RM": list(groups.values())}),
                     hide_index=True, width="stretch")
    return item_rows, list(groups.items()), ok


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
                        mine = db.get_categories(uid)
                        res = ocr_module.extract_receipt(data, categories=[c["category_name"] for c in mine])
                        cat_name, conf = classifier.predict_with_confidence(res["merchant"])
                        res["category_id"] = db.category_uuid(cat_name)
                        res["confidence"] = conf
                        res["suggestion"] = preprocessor.suggest_split(res.get("items"), res["amount"], cat_name)
                        sug = res["suggestion"]
                        if sug:                                   # category decided from the ITEMS
                            name_to_id = {c["category_name"]: c["id"] for c in mine}
                            res["category_id"] = name_to_id.get(sug["rows"][0][0], res["category_id"])
                            res["confidence"] = 1.0
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
        sug = res.get("suggestion")
        items = res.get("items") or []
        if items:
            if res.get("engine") == "gemini":
                st.info(t("Gemini read the items on this receipt. Each item has its own category - please review them."))
            else:
                st.warning(t("The items were read offline from the OCR text. This is less reliable - please check every row."))
        st.caption(t("Please check and correct the values before saving."))

        merchant = st.text_input(t("Merchant"), value=res["merchant"], key=f"cf_m_{k}")
        c1, c2 = st.columns(2)
        tx_date = c1.date_input(t("Date"), value=res["date"], key=f"cf_d_{k}")
        if res.get("date_text"):
            c1.caption(t("Printed on the receipt: {d}", d=res["date_text"]))
        if (date.today() - tx_date).days < 0 or (date.today() - tx_date).days > 400:
            c1.warning(t("This date looks unusual ({d}). Please check it.", d=str(tx_date)))
        with c2:
            amount = ui.money_input(t("Total amount (RM)"), value=float(res["amount"]), key=f"cf_a_{k}")
        default_label = id_to_label.get(res["category_id"], labels[0])
        use_items = bool(items) and not st.checkbox(t("Ignore the items and save as a single transaction"), key=f"cf_ign_{k}")
        rows, split_ok, cat_label = None, True, None
        if use_items:
            item_rows, groups, items_ok = item_editor(f"cf_{k}", items, amount, default_label)
        else:
            initial = None
            if sug and abs(amount - float(res["amount"])) < 0.005:      # only while the total is unchanged
                initial = [(ui.cat_label(c), a) for c, a in sug["rows"] if ui.cat_label(c) in cats]
            rows, split_ok = split_section(f"cf_{k}", amount, default_label, initial)
            if rows is None:
                cat_label = st.selectbox(t("Category"), labels, index=_category_index(res["category_id"]), key=f"cf_c_{k}")
        c3, c4 = st.columns(2)
        save = c3.button(t("Confirm and save"), type="primary", key=f"cf_save_{k}")
        cancel = c4.button(t("Discard"), key=f"cf_cancel_{k}")

        if save:
            if not merchant.strip() or amount <= 0:
                st.error(t("Merchant and a positive amount are required."))
            elif use_items and not items_ok:
                st.error(t("Please fix the items so they add up to the receipt total."))
            elif not use_items and rows is not None and not split_ok:
                st.error(t("The split amounts must add up exactly to the total."))
            else:
                rel = receipt_manager.save_image(uid, res["file_name"], res["data"])
                rid = db.add_receipt(uid, rel, res["file_name"], res["raw_text"], res["engine"])
                if use_items:
                    tx_ids = {}
                    for label, amt in groups:
                        tx_ids[label] = db.add_transaction(uid, merchant, tx_date, amt, cats[label],
                                                           is_manual=False, receipt_id=rid)
                    for name, amt, label in item_rows:
                        db.add_item(uid, tx_ids[label], rid, name, amt, cats[label])
                    msg = t("{n} transactions saved with {m} items.", n=len(groups), m=len(item_rows))
                else:
                    parts = rows if rows is not None else [(cat_label, amount)]
                    for label, amt in parts:
                        db.add_transaction(uid, merchant, tx_date, amt, cats[label], is_manual=False, receipt_id=rid,
                                           predicted_category_id=(cats[labels[_category_index(res["category_id"])]]
                                                                  if rows is None else None))
                    msg = (t("{n} transactions saved.", n=len(parts)) if len(parts) > 1 else t("Transaction saved."))
                analytics.detect_anomalies(uid)
                st.session_state.pop("ocr_result", None)
                st.session_state["flash_ocr"] = msg
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
    with c2:
        amount = ui.money_input(t("Amount (RM)"), value=0.0, key=f"man_a_{n}")
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
                db.add_transaction(uid, merchant, tx_date, amount, cid, is_manual=True,
                                   predicted_category_id=cid if cat_choice == auto else None)
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
                st.caption(f"{t('Uploaded')}: {ui.local_time(r['upload_date'], False)} · {r['ocr_engine'] or '—'}")
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
