"""Recurring Bills (patch #23): reminders for bills paid every month. Nothing is added automatically -
each month the user adds, changes or skips the payment, and can pause a bill and resume it later."""
from datetime import date

import streamlit as st

from src import db_manager as db, recurring
from utils import ui
from utils.i18n import t

user = ui.require_login()
uid = user["id"]
st.title(t("Recurring Bills"))
st.caption(t("Get a reminder for bills you pay every month, like Netflix, a phone plan or rent. Nothing is added automatically: each month you add, change or skip the payment, and you can pause a bill at any time."))

ui.bill_reminders(uid, "rb")

cats = ui.category_map(uid)
labels = list(cats.keys())
id_to_label = {v: k for k, v in cats.items()}
bills = db.get_bills(uid)

# ------------------------------------------------------------------ add
with st.expander(t("Add a recurring bill"), expanded=not bills):
    n = st.session_state.setdefault("bill_n", 0)
    with st.form("add_bill", clear_on_submit=True):
        name = st.text_input(t("Name"), placeholder="Netflix")
        c1, c2, c3 = st.columns(3)
        with c1:
            amt = ui.money_input(t("Amount (RM)"), value=0.0, key=f"bill_amt_{n}")
        cat = c2.selectbox(t("Category"), labels, key="bill_cat")
        day = c3.number_input(t("Day of the month"), min_value=1, max_value=31, value=date.today().day, step=1)
        ok = st.form_submit_button(t("Save bill"), type="primary")
    if ok:
        if not name.strip() or amt <= 0:
            st.error(t("A name and a positive amount are required."))
        else:
            db.add_bill(uid, name, amt, cats[cat], int(day))
            st.session_state["bill_n"] = n + 1
            st.rerun()

# ------------------------------------------------------------------ list
if bills:
    st.subheader(t("Your recurring bills"), anchor=False)
for b in bills:
    with st.container(border=True, key=f"bill_row_{b['id']}"):
        c1, c2, c3 = st.columns([4, 1, 1], vertical_alignment="center")
        state = t("Active") if b["status"] == "active" else t("Paused")
        c1.markdown(f"**{b['name']}** · {ui.money(b['amount'])}  \n"
                    f"{ui.cat_label(b['category_name'])} · {t('every month on day {d}', d=b['day_of_month'])} · {state}")
        if b["status"] == "active":
            if c2.button(t("Pause"), key=f"pause_{b['id']}"):
                db.update_bill(b["id"], uid, status="paused")
                st.rerun()
        elif c2.button(t("Resume"), key=f"resume_{b['id']}"):
            db.update_bill(b["id"], uid, status="active")
            st.rerun()
        with c3.popover(t("Edit")):
            with st.form(f"edit_bill_{b['id']}"):
                e_name = st.text_input(t("Name"), value=b["name"])
                e_amt = ui.money_input(t("Amount (RM)"), value=float(b["amount"]), key=f"e_amt_{b['id']}")
                cur = id_to_label.get(b["category_id"], labels[0])
                e_cat = st.selectbox(t("Category"), labels, index=labels.index(cur))
                e_day = st.number_input(t("Day of the month"), 1, 31, int(b["day_of_month"]))
                save = st.form_submit_button(t("Save changes"), type="primary")
                delete = st.form_submit_button(t("Delete bill"))
            if save and e_name.strip() and e_amt > 0:
                db.update_bill(b["id"], uid, name=e_name.strip(), amount=e_amt, category_id=cats[e_cat],
                               day_of_month=int(e_day))
                st.rerun()
            if delete:
                db.delete_bill(b["id"], uid)
                st.rerun()

# ------------------------------------------------------------------ suggestions from the history
sug = recurring.suggestions(uid)
if sug:
    st.subheader(t("Found in your history"), anchor=False)
    st.caption(t("You paid these with a similar amount in at least 3 of the last 4 months."))
    for i, s in enumerate(sug):
        c1, c2 = st.columns([4, 1], vertical_alignment="center")
        c1.markdown(f"**{s['name']}** · {ui.money(s['amount'])} · {ui.cat_label(s['category_name'])} · "
                    f"{t('every month on day {d}', d=s['day_of_month'])}")
        if c2.button(t("Add as recurring"), key=f"sug_{i}"):
            db.add_bill(uid, s["name"], s["amount"], s["category_id"], s["day_of_month"])
            st.rerun()
