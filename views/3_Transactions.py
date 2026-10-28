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

_view = ui.view_switcher("tx_view", {"history": t("History"), "bills": t("Recurring bills"),
                                      "price": t("Price check")}, "history")

if _view == "history":
    if st.session_state.get("tx_flash"):
        st.success(st.session_state.pop("tx_flash"))

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
        by_id = {r_["id"]: r_ for r_ in rows}            # keyed by id: same date + shop + amount no longer collide

        def _tx_label(i):
            r_ = by_id[i]
            extra = f" · {r_['item_count']} {t('items')}" if r_.get("item_count") else ""
            return f"{r_['date']} · {r_['merchant']} · {ui.cat_label(r_['category_name'])} · RM {r_['amount']:.2f}{extra}"

        r = by_id[st.selectbox(t("Select a transaction"), list(by_id.keys()), format_func=_tx_label)]
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
            st.markdown(f"**{t('Move an item to another category')}**")
            it_by_id = {i["id"]: i for i in its}
            others = [l_ for l_ in labels if cats[l_] != r["category_id"]]
            with st.form(f"move_item_{r['id']}"):
                mc1, mc2 = st.columns(2)
                it_id = mc1.selectbox(t("Item"), list(it_by_id.keys()),
                                      format_func=lambda i: f"{it_by_id[i]['item_name']} · RM {it_by_id[i]['amount']:.2f}")
                new_cat = mc2.selectbox(t("Move to"), others)
                go_move = st.form_submit_button(t("Move item"))
            if go_move and new_cat:
                db.move_item(uid, it_id, cats[new_cat])
                analytics.detect_anomalies(uid)
                st.session_state["tx_flash"] = t("Moved {item} to {cat}.", item=it_by_id[it_id]["item_name"], cat=new_cat)
                st.rerun()

if _view == "bills":
    tx_tabs.render_recurring(uid)

if _view == "price":
    tx_tabs.render_price_check(uid)
