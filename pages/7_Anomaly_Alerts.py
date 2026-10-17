"""Module 7: Anomaly Alert Management - view, review, dismiss and clear Z-score alerts (|Z| > 2.0)."""
import streamlit as st

from src import analytics, db_manager as db
from utils import ui
from utils.config import ANOMALY_Z_THRESHOLD, MIN_SAMPLES_FOR_ZSCORE
from utils.i18n import t

user = ui.require_login()
uid = user["id"]
st.title(f"{t('Anomaly Alert Management')}")
st.caption(t("Transactions are checked per category. A transaction is flagged when |Z| > {z} (needs at least {n} transactions in the category).",
             z=ANOMALY_Z_THRESHOLD, n=MIN_SAMPLES_FOR_ZSCORE))

top1, top2 = st.columns(2)
if top1.button(t("Re-scan transactions")):
    res = analytics.detect_anomalies(uid)
    st.success(t("Scan complete: {f} anomalous transaction(s), {n} new alert(s).", f=res["flagged"], n=res["new_alerts"]))
resolved = db.get_alerts(uid, "resolved")
if top2.button(t("Clear all resolved") + f" ({len(resolved)})", disabled=not resolved):
    db.clear_resolved_alerts(uid)
    st.rerun()

active = db.get_alerts(uid, "active")
st.subheader(f"{t('Active alerts')} ({len(active)})")
if not active:
    st.success(t("No active anomaly alerts."))
for a in active:
    sev = analytics.severity(a["z_score"])
    with st.container(border=True):
        c1, c2 = st.columns([4, 2])
        c1.markdown(f"**{a['merchant']}** — {ui.money(a['amount'])}  \n"
                    f"{a['date']} · {ui.cat_label(a['category_name'])}")
        direction = t("above") if a["z_score"] > 0 else t("below")
        c1.caption(f"Z = {a['z_score']:.2f} · {abs(a['z_score']):.1f} {t('standard deviations')} {direction} {t('the category mean')}")
        c2.markdown(f"{'🔴 ' if sev == 'High' else '🟠 '} **{t(sev)}**")
        b1, b2 = c2.columns(2)
        if b1.button(t("Reviewed"), key=f"rv_{a['id']}"):
            db.set_alert_status(a["id"], uid, "reviewed")
            st.rerun()
        if b2.button(t("Dismiss"), key=f"ds_{a['id']}"):
            db.set_alert_status(a["id"], uid, "dismissed")
            st.rerun()

if resolved:
    with st.expander(f"{t('Resolved alerts')} ({len(resolved)})"):
        for a in resolved:
            st.write(f"{'' if a['status'] == 'reviewed' else ''} {a['merchant']} — {ui.money(a['amount'])} · Z = {a['z_score']:.2f} · {t(a['status'])}")
