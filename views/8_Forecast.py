"""Module 8: Spending Forecast Management - Prophet forecasts per category + optional Gemini insights."""
from datetime import date

import streamlit as st

from src import analytics, db_manager as db, forecast as fc
from utils import gemini_helper, ui
from utils.config import MIN_MONTHS_FOR_FORECAST, MIN_WEEKS_FOR_FORECAST
from utils.i18n import t

user = ui.require_login()
uid = user["id"]
st.title(f"{t('Spending Forecast Management')}")
st.caption(t("Next-month forecasts per category are computed offline with Prophet from your last 12 months (at least {n} complete months per category; the current month is not counted).",
             n=MIN_MONTHS_FOR_FORECAST))

if st.button(t("Recalculate forecasts"), type="primary"):
    with st.spinner(t("Forecasting...")):
        try:
            res = fc.generate_forecasts(uid)
            st.session_state.pop("ai_insights", None)
            if res["saved"]:
                st.success(t("{n} forecast(s) saved for {m}.", n=res["saved"], m=res["target"]))
            else:
                st.warning(t("Not enough history to forecast yet. Record transactions across at least {n} different months.", n=MIN_MONTHS_FOR_FORECAST))
            if res["skipped"]:
                st.caption(t("Skipped (not enough history): ") + ", ".join(ui.cat_label(x) for x in res["skipped"]))
        except Exception as e:
            st.error(f"{t('Forecast failed')}: {e}")

saved = db.get_forecasts(uid)
months = sorted({f["forecast_month"] for f in saved}, reverse=True)
if not months:
    st.info(t("No forecasts saved yet. Press Recalculate forecasts."))
    st.stop()

month = st.selectbox(t("Forecast month"), months)
rows = db.get_forecasts(uid, month)
cur_actual = analytics.monthly_summary(uid, analytics.month_str(date.today()))
cur_map = dict(zip(cur_actual["category_id"], cur_actual["total"])) if not cur_actual.empty else {}

st.metric(t("Total forecast"), ui.money(sum(r["forecast_amount"] for r in rows)))
cols = st.columns(3)
for i, r in enumerate(rows):
    with cols[i % 3]:
        with st.container(border=True):
            st.markdown(f"**{ui.cat_label(r['category_name'])}**")
            st.markdown(f"### {ui.money(r['forecast_amount'])}")
            st.caption(f"{t('Range')}: {ui.money(r['confidence_lower'])} – {ui.money(r['confidence_upper'])}")
            actual = float(cur_map.get(r["category_id"], 0.0))
            if actual > 0:
                diff = (r["forecast_amount"] - actual) / actual * 100
                arrow = "" if diff > 5 else ("" if diff < -5 else "")
                word = t("higher") if diff > 5 else (t("lower") if diff < -5 else t("similar"))
                st.caption(f"{arrow} {t('vs this month')} ({ui.money(actual)}): {word}")
            if st.button(t("Delete"), key=f"fd_{r['id']}"):
                db.delete_forecast(r["id"], uid)
                st.rerun()

st.subheader(f"{t('AI spending insights')}")
if not gemini_helper.is_configured():
    st.caption(t("Optional: add GEMINI_API_KEY to .env to get written insights when online."))
elif not ui.online_status():
    st.caption(t("Offline — showing the Prophet forecast only. AI insights appear when you are online."))
else:
    if st.button(t("Generate AI insights")):
        with st.spinner(t("Asking Gemini...")):
            language = "Bahasa Malaysia" if st.session_state.get("lang") == "ms" else "English"
            st.session_state["ai_insights"] = fc.get_ai_insights(uid, month, language) or t("AI insights are unavailable right now.")
    if st.session_state.get("ai_insights"):
        st.info(st.session_state["ai_insights"])
