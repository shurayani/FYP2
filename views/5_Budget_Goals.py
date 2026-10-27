"""Module 5: Budget Goal Management - monthly budget per category, budget vs actual, history."""
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from src import analytics, db_manager as db
from utils import ui
from utils.i18n import t

user = ui.require_login()
uid = user["id"]
st.title(f"{t('Budget Goal Management')}")

cats = ui.category_map(uid)
tab_cur, tab_hist = st.tabs([t("Current Month"), t("History")])

with tab_cur:
    months = ui.month_options(12, 1)
    month = st.selectbox(t("Month"), months, index=months.index(analytics.month_str(date.today())))

    with st.form("budget_form", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 2, 1])
        cat = c1.selectbox(t("Category"), list(cats.keys()))
        bud_n = st.session_state.setdefault("bud_n", 0)
        with c2:
            amt = ui.money_input(t("Monthly budget (RM)"), value=0.0, key=f"bud_a_{bud_n}")
        go = c3.form_submit_button(t("Save goal"), type="primary")
    if go:
        if amt <= 0:
            st.error(t("Budget must be greater than zero."))
        else:
            db.upsert_budget(uid, cats[cat], month, amt)
            st.success(t("Budget goal saved."))
            st.session_state["bud_n"] = bud_n + 1
            st.rerun()

    bva = analytics.budget_vs_actual(uid, month)
    if bva.empty:
        st.info(t("No budget goals for this month yet."))
    else:
        tb, ta = bva["budget"].sum(), bva["actual"].sum()
        pct = ta / tb * 100 if tb else 0
        st.markdown(f"**{t('Overall budget')}**: {ui.money(ta)} / {ui.money(tb)} ({pct:.0f}%)")
        st.markdown(ui.progress_bar(pct, analytics.progress_colour(pct)), unsafe_allow_html=True)
        st.write("")
        for _, b in bva.iterrows():
            with st.container(border=True):
                h1, h2 = st.columns([3, 2])
                h1.markdown(f"**{ui.cat_label(b['category_name'])}**")
                h2.caption(f"{t('Remaining')}: {ui.money(b['remaining'])}")
                st.markdown(ui.progress_bar(b["pct"], analytics.progress_colour(b["pct"])), unsafe_allow_html=True)
                st.caption(f"{t('Spent')} {ui.money(b['actual'])} / {t('Budget')} {ui.money(b['budget'])} · {b['pct']:.0f}%")
                e1, e2, e3 = st.columns([2, 1, 1])
                with e1:
                    new_amt = ui.money_input("", value=float(b["budget"]), key=f"ba_{b['budget_id']}")
                if e2.button(t("Update"), key=f"bu_{b['budget_id']}"):
                    if new_amt > 0:
                        db.update_budget(b["budget_id"], uid, new_amt)
                    st.rerun()
                if e3.button(t("Remove"), key=f"bd_{b['budget_id']}"):
                    db.delete_budget(b["budget_id"], uid)
                    st.rerun()

with tab_hist:
    rows = []
    cur = analytics.month_str(date.today())
    for i in range(5, -1, -1):
        m = analytics.add_months(cur, -i)
        for _, r in analytics.budget_vs_actual(uid, m).iterrows():
            rows.append({"month": m, "category": ui.cat_label(r["category_name"]), "type": t("Budget"), "RM": r["budget"]})
            rows.append({"month": m, "category": ui.cat_label(r["category_name"]), "type": t("Spent"), "RM": r["actual"]})
    if not rows:
        st.info(t("No budget history in the last 6 months."))
    else:
        df = pd.DataFrame(rows)
        fig = px.bar(df, x="category", y="RM", color="type", barmode="group", facet_col="month", facet_col_wrap=3)
        fig.update_xaxes(matches=None, showticklabels=True)
        st.plotly_chart(fig, width="stretch")
