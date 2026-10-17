"""Module 6: Spending Report Management - generate, view, regenerate and delete monthly reports."""
import json
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from src import analytics, db_manager as db
from utils import ui
from utils.i18n import t

user = ui.require_login()
uid = user["id"]
st.title(f"{t('Spending Report Management')}")

months = ui.month_options(12, 0)
c1, c2 = st.columns([2, 1])
month = c1.selectbox(t("Month"), months)
existing = {r["report_month"]: r for r in db.get_reports(uid)}
if c2.button(t("Regenerate report") if month in existing else t("Generate report"), type="primary"):
    db.save_report(uid, month, analytics.build_report(uid, month))
    st.success(t("Report saved."))
    st.rerun()

st.subheader(t("Saved reports"))
reports = db.get_reports(uid)
if not reports:
    st.info(t("No reports saved yet. Choose a month and press Generate report."))

for r in reports:
    data = json.loads(r["report_data"])
    with st.expander(f"{r['report_month']} — {ui.money(data['total'])}  ·  {t('generated')} {r['generated_at'][:16].replace('T', ' ')}",
                     expanded=(r["report_month"] == month)):
        k = st.columns(4)
        k[0].metric(t("Total spent"), ui.money(data["total"]))
        k[1].metric(t("Highest category"), ui.cat_label(data["top_category"]) if data["top_category"] else "—")
        k[2].metric(t("Top merchant"), data["top_merchants"][0]["merchant"] if data["top_merchants"] else "—")
        k[3].metric(t("Average per day"), ui.money(data["avg_daily"]))

        if data["categories"]:
            cdf = pd.DataFrame(data["categories"])
            cdf["category"] = cdf["category"].map(ui.cat_label)
            g1, g2 = st.columns(2)
            g1.plotly_chart(px.bar(cdf, x="category", y="total", labels={"total": "RM", "category": t("Category")}),
                            width="stretch", key=f"bar_{r['id']}")
            g2.plotly_chart(px.pie(cdf, names="category", values="total", hole=0.35),
                            width="stretch", key=f"pie_{r['id']}")
            show = cdf.rename(columns={"category": t("Category"), "total": t("Spent") + " (RM)", "count": t("Transactions"),
                                       "share": t("Share") + " (%)", "budget": t("Budget") + " (RM)",
                                       "variance": t("Variance") + " (RM)"})
            st.dataframe(show, width="stretch", hide_index=True)
        if data["daily"]:
            st.plotly_chart(px.line(pd.DataFrame(data["daily"]), x="date", y="total", markers=True,
                                    labels={"total": "RM", "date": t("Date")}), width="stretch", key=f"daily_{r['id']}")
        st.markdown(f"**{t('Month-on-month trend')}**")
        st.plotly_chart(px.line(pd.DataFrame(data["trend_months"]), x="month", y="total", markers=True,
                                labels={"total": "RM", "month": t("Month")}), width="stretch", key=f"trend_{r['id']}")
        if data["top_merchants"]:
            st.markdown(f"**{t('Top merchants')}**")
            st.dataframe(pd.DataFrame(data["top_merchants"]), width="stretch", hide_index=True)
        for line in data["trends"]:
            st.write("• " + line)
        b1, b2 = st.columns(2)
        if b1.button(t("Regenerate"), key=f"rg_{r['id']}"):
            db.save_report(uid, r["report_month"], analytics.build_report(uid, r["report_month"]))
            st.rerun()
        if b2.button(t("Delete report"), key=f"rd_{r['id']}"):
            db.delete_report(r["id"], uid)
            st.rerun()
