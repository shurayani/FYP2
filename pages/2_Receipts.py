"""Module 2: Receipt Management - upload / camera, hybrid OCR, confirmation form, manual entry, gallery."""
from datetime import date

import streamlit as st

from src import analytics, classifier, db_manager as db, ocr_module, receipt_manager
from utils import ui
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


# ------------------------------------------------------------------------- OCR upload
with tab_ocr:
    online = ui.online_status()
    st.caption(t("Gemini AI is used when online; PaddleOCR is used automatically when offline or if Gemini fails.")
               + "  " + (("🟢 " + t("Online")) if online else ("🔴 " + t("Offline"))))
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
                        res["category_id"] = classifier.predict_category_id(res["merchant"])
                        st.session_state["ocr_result"] = {**res, "file_name": fname, "data": data}
                    except Exception as e:
                        st.session_state.pop("ocr_result", None)
                        st.error(f"{t('Extraction failed')}: {e}")

    res = st.session_state.get("ocr_result")
    if res:
        st.divider()
        engine_label = "Gemini AI" if res["engine"] == "gemini" else "PaddleOCR"
        st.success(f"{t('Extracted with')}: **{engine_label}** ({res['seconds']} s)")
        if res.get("note"):
            st.info(res["note"])
        if not res.get("complete"):
            st.warning(t("Some fields could not be read reliably. Please complete them below."))
        st.caption(t("Please check and correct the values before saving."))
        with st.form("confirm_form"):
            merchant = st.text_input(t("Merchant"), value=res["merchant"])
            c1, c2 = st.columns(2)
            tx_date = c1.date_input(t("Date"), value=res["date"])
            amount = c2.number_input(t("Total amount (RM)"), min_value=0.0, value=float(res["amount"]), step=0.10, format="%.2f")
            cat_label = st.selectbox(t("Category"), labels, index=_category_index(res["category_id"]))
            c3, c4 = st.columns(2)
            save = c3.form_submit_button(t("Confirm and save"), type="primary")
            cancel = c4.form_submit_button(t("Discard"))
        if save:
            if not merchant.strip() or amount <= 0:
                st.error(t("Merchant and a positive amount are required."))
            else:
                rel = receipt_manager.save_image(uid, res["file_name"], res["data"])
                rid = db.add_receipt(uid, rel, res["file_name"], res["raw_text"], res["engine"])
                db.add_transaction(uid, merchant, tx_date, amount, cats[cat_label], is_manual=False, receipt_id=rid)
                analytics.detect_anomalies(uid)
                st.session_state.pop("ocr_result", None)
                st.success(t("Transaction saved."))
                st.rerun()
        if cancel:
            st.session_state.pop("ocr_result", None)
            st.rerun()

# ------------------------------------------------------------------------- manual entry
with tab_manual:
    st.caption(t("Record a transaction without a receipt. Leave the category on Auto to let the classifier decide."))
    auto = t("Auto (classify automatically)")
    with st.form("manual_form", clear_on_submit=True):
        merchant = st.text_input(t("Merchant"))
        c1, c2 = st.columns(2)
        tx_date = c1.date_input(t("Date"), value=date.today(), key="m_date")
        amount = c2.number_input(t("Amount (RM)"), min_value=0.0, value=0.0, step=0.10, format="%.2f", key="m_amt")
        cat_choice = st.selectbox(t("Category"), [auto] + labels, key="m_cat")
        go = st.form_submit_button(t("Save transaction"), type="primary")
    if go:
        if not merchant.strip() or amount <= 0:
            st.error(t("Merchant and a positive amount are required."))
        else:
            cid = classifier.predict_category_id(merchant) if cat_choice == auto else cats[cat_choice]
            if cid not in id_to_label:                       # predicted category missing/deleted -> first available
                cid = list(cats.values())[0]
            db.add_transaction(uid, merchant, tx_date, amount, cid, is_manual=True)
            analytics.detect_anomalies(uid)
            st.success(f"{t('Transaction saved.')} {t('Category')}: {id_to_label[cid]}")

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
                if img:
                    st.image(img, width="stretch")
                else:
                    st.caption(t("Image file not found on this device."))
                st.caption(f"{t('Uploaded')}: {r['upload_date'][:10]} · {r['ocr_engine'] or '—'}")
                if r["transaction_id"]:
                    st.caption(f"{t('Linked transaction')}: {r['tx_merchant']} · {ui.money(r['tx_amount'])}")
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
