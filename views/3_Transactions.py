"""Module 3: Transaction Management - history with filters, correction, delete, manual add, CSV export."""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src import analytics, classifier, db_manager as db
from utils import tx_tabs, ui
from utils.i18n import t

user = ui.require_login()
uid = user["id"]
st.title(f"{t('Transaction Management')}")
ui.budget_banner(uid)

cats = ui.category_map(uid)
labels = list(cats.keys())
id_to_label = {v: k for k, v in cats.items()}

tab_hist, tab_bills, tab_price = st.tabs([t("History"), t("Recurring bills"), t("Price check")])

with tab_hist:

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
            t("Items"): df["item_count"],
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
            add_n = st.session_state.setdefault("add_tx_n", 0)          # new key after every save = empty field
            with c2:
                a = ui.money_input(t("Amount (RM)"), value=0.0, key=f"add_a_{add_n}")
            c = st.selectbox(t("Category"), [auto] + labels, key="add_c")
            ok = st.form_submit_button(t("Add"), type="primary")
        if ok:
            if not m.strip() or a <= 0:
                st.error(t("Merchant and a positive amount are required."))
            else:
                cid = classifier.predict_category_id(m) if c == auto else cats[c]
                if cid not in id_to_label:
                    cid = list(cats.values())[0]
                db.add_transaction(uid, m, d, a, cid, is_manual=True,
                                   predicted_category_id=cid if c == auto else None)
                analytics.detect_anomalies(uid)
                st.success(t("Transaction saved."))
                st.session_state["add_tx_n"] = add_n + 1
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
            with c2:
                a = ui.money_input(t("Amount (RM)"), value=float(r["amount"]), key=f"edit_a_{r['id']}")
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


    # ------------------------------------------------------------------ items inside the selected transaction
    if rows:
        its = db.get_items(uid, transaction_id=r["id"])
        if its:
            st.subheader(t("Items on this transaction"))
            st.dataframe(pd.DataFrame({t("Item"): [i["item_name"] for i in its], "RM": [round(i["amount"], 2) for i in its],
                                       t("Category"): [ui.cat_label(i["category_name"]) for i in its]}),
                         width="stretch", hide_index=True)
            if abs(sum(i["amount"] for i in its) - float(r["amount"])) > 0.005:
                st.caption(t("Item prices are shown before discounts and fees. The transaction amount is what you paid."))

with tab_bills:
    tx_tabs.render_recurring(uid)

with tab_price:
    tx_tabs.render_price_check(uid)
