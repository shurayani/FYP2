"""Module 4: Expense Category Management - 7 system categories (read-only) + custom categories."""
import pandas as pd
import streamlit as st

from src import db_manager as db
from utils import ui
from utils.i18n import t

user = ui.require_login()
uid = user["id"]
st.title(f"{t('Expense Category Management')}")

summary = db.category_summary(uid)
system = [c for c in summary if c["is_system"]]
custom = [c for c in summary if not c["is_system"]]

st.subheader(t("System categories (read-only)"))
st.dataframe(pd.DataFrame({t("Category"): [ui.cat_label(c["category_name"]) for c in system],
                           t("Transactions"): [c["tx_count"] for c in system],
                           t("Total spent") + " (RM)": [round(c["total"], 2) for c in system]}),
             width="stretch", hide_index=True)

st.subheader(t("Your custom categories"))
with st.form("new_cat", clear_on_submit=True):
    name = st.text_input(t("New category name"))
    add = st.form_submit_button(t("Create category"), type="primary")
if add:
    if len(name.strip()) < 2:
        st.error(t("Please enter a category name."))
    elif db.category_name_taken(name, uid):
        st.error(t("A category with that name already exists."))
    else:
        db.add_category(name, uid)
        st.success(t("Category created."))
        st.rerun()

if not custom:
    st.info(t("You have no custom categories yet."))
all_cats = db.get_categories(uid)
for c in custom:
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 2, 2])
        new_name = c1.text_input(t("Name"), value=c["category_name"], key=f"rn_{c['id']}", label_visibility="collapsed")
        c2.caption(f"{c['tx_count']} {t('transaction(s)')} · {ui.money(c['total'])}")
        if c1.button(t("Rename"), key=f"rnb_{c['id']}"):
            if new_name.strip() and new_name.strip().lower() != c["category_name"].lower() and db.category_name_taken(new_name, uid):
                st.error(t("A category with that name already exists."))
            elif new_name.strip():
                db.rename_category(c["id"], new_name, uid)
                st.rerun()
        if c3.button(t("Delete"), key=f"dl_{c['id']}"):
            st.session_state["confirm_delete_cat"] = c["id"]
        if st.session_state.get("confirm_delete_cat") == c["id"]:
            n = c["tx_count"]
            fallbacks = {ui.cat_label(x["category_name"]): x["id"] for x in all_cats if x["id"] != c["id"]}
            if n:
                st.warning(t("{n} transaction(s) use this category. Choose a fallback category to reassign them to.", n=n))
                fb = st.selectbox(t("Reassign to"), list(fallbacks.keys()), key=f"fb_{c['id']}")
            else:
                fb = None
            d1, d2 = st.columns(2)
            if d1.button(t("Confirm delete"), key=f"cd_{c['id']}", type="primary"):
                db.delete_category(c["id"], uid, reassign_to=fallbacks[fb] if fb else None)
                st.session_state.pop("confirm_delete_cat", None)
                st.rerun()
            if d2.button(t("Cancel"), key=f"cc_{c['id']}"):
                st.session_state.pop("confirm_delete_cat", None)
                st.rerun()
