"""Module 3: Transaction Management - history with filters, correction, delete, manual add, CSV export."""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src import analytics, classifier, db_manager as db
from utils import ui
from utils.i18n import t

user = ui.require_login()
uid = user["id"]
st.title(f"{t('Transaction Management')}")

cats = ui.category_map(uid)
labels = list(cats.keys())
id_to_label = {v: k for k, v in cats.items()}

# ------------------------------------------------------------------ filters
with st.expander(t("Filters"), expanded=True):
    f1, f2, f3, f4 = st.columns(4)
    all_rows = db.get_transactions(uid)
    default_start = date.today() - timedelta(days=365)
    rng = f1.date_input(t("Date range"), value=(default_start, date.today()))
    cat_sel = f2.selectbox(t("Category"), [t("All")] + labels)
    max_amt = f3.number_input(t("Maximum amount (RM)"), min_value=0.0, value=0.0, step=10.0,
                              help=t("0 = no limit"))
    method = f4.selectbox(t("Entry method"), [t("All"), t("Manual"), "OCR"])

start, end = (rng if isinstance(rng, (tuple, list)) and len(rng) == 2 else (default_start, date.today()))
rows = db.get_transactions(uid, start=start, end=end,
                           category_id=None if cat_sel == t("All") else cats[cat_sel],
                           max_amount=max_amt if max_amt > 0 else None,
                           is_manual=None if method == t("All") else (1 if method == t("Manual") else 0))

# ------------------------------------------------------------------ table
if rows:
    df = pd.DataFrame(rows)
    view = pd.DataFrame({
        t("Date"): df["date"], t("Merchant"): df["merchant"],
        t("Category"): df["category_name"].map(ui.cat_label), "RM": df["amount"].round(2),
        t("Source"): df["is_manual"].map({1: t("Manual"), 0: "OCR"}),
        t("Anomaly"): df["is_anomaly"].map({1: "Yes", 0: ""}),
    })
    st.caption(f"{len(view)} {t('transaction(s)')} · {t('Total')}: {ui.money(df['amount'].sum())}")
    st.dataframe(view, width="stretch", hide_index=True)
    st.download_button(t("Export CSV"), view.to_csv(index=False).encode("utf-8"),
                       file_name=f"ipecs_transactions_{date.today()}.csv", mime="text/csv")
else:
    st.info(t("No transactions match the current filters."))

# ------------------------------------------------------------------ add manually
with st.expander(t("Add transaction manually")):
    auto = t("Auto (classify automatically)")
    with st.form("add_tx", clear_on_submit=True):
        m = st.text_input(t("Merchant"))
        c1, c2 = st.columns(2)
        d = c1.date_input(t("Date"), value=date.today(), key="add_d")
        a = c2.number_input(t("Amount (RM)"), min_value=0.0, step=0.10, format="%.2f", key="add_a")
        c = st.selectbox(t("Category"), [auto] + labels, key="add_c")
        ok = st.form_submit_button(t("Add"), type="primary")
    if ok:
        if not m.strip() or a <= 0:
            st.error(t("Merchant and a positive amount are required."))
        else:
            cid = classifier.predict_category_id(m) if c == auto else cats[c]
            if cid not in id_to_label:
                cid = list(cats.values())[0]
            db.add_transaction(uid, m, d, a, cid, is_manual=True)
            analytics.detect_anomalies(uid)
            st.success(t("Transaction saved."))
            st.rerun()

# ------------------------------------------------------------------ edit / delete
if rows:
    st.subheader(t("Correct or delete a transaction"))
    opts = {f"{r['date']} · {r['merchant']} · RM {r['amount']:.2f}": r for r in rows}
    choice = st.selectbox(t("Select a transaction"), list(opts.keys()))
    r = opts[choice]
    with st.form(f"edit_{r['id']}"):
        m = st.text_input(t("Merchant"), value=r["merchant"])
        c1, c2 = st.columns(2)
        d = c1.date_input(t("Date"), value=date.fromisoformat(r["date"]))
        a = c2.number_input(t("Amount (RM)"), min_value=0.0, value=float(r["amount"]), step=0.10, format="%.2f")
        cur = id_to_label.get(r["category_id"], labels[0])
        c = st.selectbox(t("Category"), labels, index=labels.index(cur))
        b1, b2 = st.columns(2)
        save = b1.form_submit_button(t("Save changes"), type="primary")
        delete = b2.form_submit_button(t("Delete transaction"))
    if save:
        if not m.strip() or a <= 0:
            st.error(t("Merchant and a positive amount are required."))
        else:
            db.update_transaction(r["id"], uid, merchant=m.strip(), date=d, amount=a, category_id=cats[c])
            analytics.detect_anomalies(uid)
            st.success(t("Transaction updated."))
            st.rerun()
    if delete:
        db.delete_transaction(r["id"], uid)
        analytics.detect_anomalies(uid)
        st.success(t("Transaction deleted."))
        st.rerun()
