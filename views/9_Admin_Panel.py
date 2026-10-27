"""Admin Panel (FR14): user management, system overview, category management, transaction oversight.
Access is enforced by a session role check (NFR09)."""
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from src import auth, db_manager as db, ocr_module
from utils import gemini_helper, ui
from utils.i18n import t

user = ui.require_login(admin_only=True)


def _push_user_change(user_id):
    """Send an account (de)activation to Supabase now, so the cloud and other devices see it."""
    try:
        from src import sync_manager
        if sync_manager.check_connection()[0]:
            sync_manager.push_pending(user_id, {"pushed": 0, "pulled": 0, "conflicts": []})
    except Exception:
        pass                                       # stays pending; sent at that user's next sync

st.title(f"{t('Admin Panel')}")

from src import cloud_mode as _cloud_mode
_tab_names = [t("User Management"), t("System Overview"), t("Category Management"), t("Transaction Oversight")]
if _cloud_mode.enabled():                          # diagnosis tab: cloud version only
    _tab_names.append("Cloud / Sync check")
_tabs = st.tabs(_tab_names)
tab_users, tab_sys, tab_cat, tab_tx = _tabs[:4]
tab_cloud = _tabs[4] if len(_tabs) > 4 else None

# ------------------------------------------------------------------ user management
with tab_users:
    users = [u for u in db.list_users() if u["role"] == "user"]
    k = st.columns(3)
    k[0].metric(t("Registered users"), len(users))
    k[1].metric(t("Active"), sum(1 for u in users if u["is_active"]))
    k[2].metric(t("Deactivated"), sum(1 for u in users if not u["is_active"]))
    q = st.text_input(t("Search users"))
    shown = [u for u in users if q.lower() in u["username"].lower() or q.lower() in u["email"].lower()]
    if shown:
        st.dataframe(pd.DataFrame({
            "ID": [u["id"][:8] for u in shown], t("Username"): [u["username"] for u in shown],
            t("Email"): [u["email"] for u in shown],
            t("Status"): [t("Active") if u["is_active"] else t("Deactivated") for u in shown],
            t("Registered"): [ui.local_time(u["created_at"], False) for u in shown],
            t("Transactions"): [u["tx_count"] for u in shown]}), width="stretch", hide_index=True)
        opts = {f"{u['username']} ({u['email']})": u for u in shown}
        pick = opts[st.selectbox(t("Select a user"), list(opts.keys()))]
        if pick["is_active"]:
            if st.button(t("Deactivate account")):
                auth.set_active(pick["id"], False)
                _push_user_change(pick["id"])
                st.rerun()
        else:
            if st.button(t("Reactivate account")):
                auth.set_active(pick["id"], True)
                _push_user_change(pick["id"])
                st.rerun()
    else:
        st.info(t("No users found."))

# ------------------------------------------------------------------ system overview
with tab_sys:
    k = st.columns(4)
    k[0].metric(t("Total users"), len([u for u in db.list_users() if u["role"] == "user"]))
    k[1].metric(t("Total transactions"), db.count_transactions_all())
    k[2].metric(t("Receipts uploaded"), db.count_receipts_all())
    k[3].metric(t("Active anomaly alerts"), db.count_active_alerts_all())
    all_tx = pd.DataFrame(db.get_transactions())
    c1, c2 = st.columns(2)
    if all_tx.empty:
        st.caption(t("No transactions yet."))
    else:
        by_cat = all_tx.groupby("category_name").size().reset_index(name="count")
        by_cat["category_name"] = by_cat["category_name"].map(ui.cat_label)
        c1.plotly_chart(px.bar(by_cat, x="category_name", y="count", title=t("Transactions by category")),
                        width="stretch")
        daily = all_tx.groupby("date").size().reset_index(name="count")
        c2.plotly_chart(px.line(daily, x="date", y="count", title=t("Daily activity"), markers=True),
                        width="stretch")
    st.subheader(t("System integrity"))
    try:
        db.count_transactions_all()
        db_ok = True
    except Exception:
        db_ok = False
    st.write(f"{'🟢 ' if db_ok else '🔴 '} {t('Database')}: {'OK' if db_ok else 'ERROR'}")
    st.write(f"{'🟢 ' if ocr_module.paddle_available() else '🟠 '} {t('OCR service (PaddleOCR)')}: "
             f"{t('installed') if ocr_module.paddle_available() else t('not installed')}")
    st.write(f"{'🟢 ' if gemini_helper.is_configured() else '🟠 '} {t('AI module (Gemini)')}: "
             f"{t('API key configured') if gemini_helper.is_configured() else t('no API key')}")

# ------------------------------------------------------------------ category management
with tab_cat:
    summ = db.category_summary_all()
    st.dataframe(pd.DataFrame({
        t("Category"): [ui.cat_label(c["category_name"]) for c in summ],
        t("Type"): [t("System") if c["is_system"] else t("Custom") for c in summ],
        t("Transactions"): [c["tx_count"] for c in summ],
        t("Total") + " (RM)": [round(c["total"], 2) for c in summ]}), width="stretch", hide_index=True)
    with st.form("sys_cat", clear_on_submit=True):
        n = st.text_input(t("New system category name"))
        add = st.form_submit_button(t("Create system category"), type="primary")
    if add:
        if len(n.strip()) < 2:
            st.error(t("Please enter a category name."))
        elif any(c["category_name"].lower() == n.strip().lower() and c["is_system"] for c in summ):
            st.error(t("A category with that name already exists."))
        else:
            db.add_category(n, is_system=True)
            st.rerun()
    editable = [c for c in summ if not (c["is_system"] and c["category_name"] in db.SYSTEM_CATEGORIES)]
    if editable:
        st.caption(t("The seven predefined categories are protected. Other categories can be renamed or deleted."))
        pick = {f"{c['category_name']} ({t('System') if c['is_system'] else t('Custom')})": c for c in editable}
        c = pick[st.selectbox(t("Select a category"), list(pick.keys()))]
        new_name = st.text_input(t("Rename to"), value=c["category_name"])
        b1, b2 = st.columns(2)
        if b1.button(t("Rename"), key="adm_rn") and new_name.strip():
            db.rename_category(c["id"], new_name, c["user_id"])
            st.rerun()
        fallback = db.category_uuid("Food and Beverage")
        if b2.button(t("Delete"), key="adm_del"):
            db.delete_category(c["id"], c["user_id"], reassign_to=fallback if c["tx_count"] else None)
            st.rerun()

# ------------------------------------------------------------------ transaction oversight
with tab_tx:
    users_all = [u for u in db.list_users() if u["role"] == "user"]
    f1, f2, f3, f4 = st.columns(4)
    u_sel = f1.selectbox(t("User"), [t("All")] + [u["username"] for u in users_all])
    cats = {ui.cat_label(c["category_name"]): c["id"] for c in db.get_all_categories()}
    c_sel = f2.selectbox(t("Category"), [t("All")] + list(cats.keys()), key="adm_cat_f")
    rng = f3.date_input(t("Date range"), value=(date.today() - timedelta(days=365), date.today()), key="adm_rng")
    max_amt = f4.number_input(t("Maximum amount (RM)"), min_value=0.0, value=0.0, key="adm_max")
    uid_filter = None if u_sel == t("All") else next(u["id"] for u in users_all if u["username"] == u_sel)
    s, e = (rng if isinstance(rng, (tuple, list)) and len(rng) == 2 else (None, None))
    rows = db.get_transactions(uid_filter, start=s, end=e, category_id=None if c_sel == t("All") else cats[c_sel],
                               max_amount=max_amt if max_amt > 0 else None)
    if rows:
        df = pd.DataFrame(rows)
        view = pd.DataFrame({t("User"): df["username"], t("Date"): df["date"], t("Merchant"): df["merchant"],
                             t("Category"): df["category_name"].map(ui.cat_label), "RM": df["amount"].round(2),
                             t("Anomaly"): df["is_anomaly"].map({1: "Yes", 0: ""})})
        st.dataframe(view, width="stretch", hide_index=True)
        st.download_button(t("Export CSV"), view.to_csv(index=False).encode("utf-8"),
                           file_name="ipecs_admin_transactions.csv", mime="text/csv")
        st.subheader(t("Flag a suspicious transaction"))
        opts = {f"{r['username']} · {r['date']} · {r['merchant']} · RM {r['amount']:.2f}": r for r in rows[:200]}
        r = opts[st.selectbox(t("Select a transaction"), list(opts.keys()))]
        if st.button(t("Flag for review")):
            if db.get_alert_for_transaction(r["id"]):
                st.info(t("This transaction already has an alert."))
            else:
                db.add_alert(r["user_id"], r["id"], r["z_score"] or 0.0)
                st.success(t("Alert created for the user."))
    else:
        st.info(t("No transactions match the current filters."))


# ------------------------------------------------------------------ cloud / sync check (patch #18)
if tab_cloud is not None:
    with tab_cloud:
        from src import cloud_mode
        info = cloud_mode.check()
        c1, c2 = st.columns(2)
        c1.metric("Cloud mode (IPECS_CLOUD)", "ON" if info["cloud_mode"] else "OFF")
        c2.metric("Supabase configured", "Yes" if info["supabase_configured"] else "No")
        st.caption(f"Database on this server: {info['db_path']}")
        c3, c4 = st.columns(2)
        with c3:
            st.markdown(f"**Accounts in this server's database ({len(info['local_users'])})**")
            st.write(", ".join(info["local_users"]) or "none")
        with c4:
            st.markdown(f"**Accounts in Supabase ({len(info['remote_users'])})**")
            if info["remote_error"]:
                st.error("Supabase could not be read: " + info["remote_error"])
            else:
                st.write(", ".join(info["remote_users"]) or "none")
        missing = sorted(set(info["remote_users"]) - set(info["local_users"]))
        if missing:
            st.warning("In Supabase but NOT on this server (cannot log in here yet): " + ", ".join(missing))
        st.markdown("**Last restore from Supabase**")
        st.json(info["last_restore"] or {"note": "no restore has run since this server started"})
        if st.button("Restore from Supabase now", type="primary"):
            with st.spinner("Copying accounts and records from Supabase..."):
                res = cloud_mode.restore_all()
            if res["error"]:
                st.error("Restore failed: " + res["error"])
            else:
                st.success(f"Restored {res['restored']} record(s); {res['failed']} could not be copied.")
            if res["errors"]:
                st.code("\n".join(res["errors"]))
