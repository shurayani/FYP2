"""IPECS - Streamlit entry point: navigation, sidebar (dark mode + language toggles) and Dashboard.
Run with:  streamlit run app.py"""
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="IPECS", page_icon="💸", layout="wide")

from src import analytics, auth, cloud_mode, db_manager as db, forecast as fc
from utils import ui
from utils.i18n import t

auth.init()                                    # create DB, seed 7 categories + admin on first launch


@st.cache_resource(show_spinner="Loading saved accounts and transactions...")
def _restore_from_supabase_once():
    """Cloud only (IPECS_CLOUD = "1"): the cloud disk was wiped by a restart -> bring everything back from Supabase."""
    if cloud_mode.ready() and cloud_mode.local_user_count() == 0:
        return cloud_mode.restore_all()
    return None


@st.cache_resource(show_spinner="Preparing the demo account (first start only, about a minute)...")
def _seed_demo_once():
    """Optional (IPECS_DEMO = "1"): create demo / demo123 with sample data once per server start."""
    if db.get_user_by_username("demo"):
        return True
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent
    done = subprocess.run([sys.executable, str(root / "scripts" / "seed_demo_data.py")], cwd=str(root),
                          capture_output=True, text=True)
    return done.returncode == 0


import os                                      # noqa: E402
_restored = _restore_from_supabase_once()
if _restored and _restored.get("error"):
    _restore_from_supabase_once.clear()        # Supabase was unreachable: try again on the next page load
    st.warning("Saved data could not be loaded from Supabase yet: " + _restored["error"])
if os.getenv("IPECS_DEMO") == "1":
    _seed_demo_once()

# language comes from the BM toggle (ON = Bahasa Malaysia, OFF = English)
st.session_state["lang"] = "ms" if st.session_state.get("lang_bm", False) else "en"

# ----------------------------------------------------------------------------- styling
BASE_CSS = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
h1 { font-size: 1.85rem !important; font-weight: 700 !important; letter-spacing: -0.3px; }
h2, h3 { font-weight: 650 !important; }

/* sidebar: profile card + light-blue page boxes */
[data-testid="stSidebar"] { border-right: 1px solid #cfe2f5; background: #f4f9fe; }
.profile-card { display:flex; align-items:center; gap:12px; padding:0.8rem 0.9rem; margin-bottom:0.5rem;
    background:#ffffff; border:1px solid #cfe2f5; border-radius:12px; }
.profile-avatar { width:42px; height:42px; border-radius:50%; background:#2E74B5; color:#ffffff;
    display:flex; align-items:center; justify-content:center; font-weight:700; font-size:1.1rem; }
.profile-name { font-weight:650; line-height:1.2; color:#1f3b57; }
.profile-role { font-size:0.75rem; color:#5b7690; text-transform:uppercase; letter-spacing:.6px; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {
    border: 1px solid #cfe2f5; border-radius: 8px; padding: 0.5rem 0.85rem; margin-bottom: 4px;
    background: #e6f1fc; transition: all .15s ease;
}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p { color:#1f4e79; font-weight:500; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover { background:#d3e6f9; border-color:#2E74B5; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] { background:#2E74B5; border-color:#2E74B5; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"] p { color:#ffffff; font-weight:600; }

.nav-active { box-sizing:border-box; height:45px; display:flex; align-items:center; border:1px solid #2E74B5;
    border-radius:8px; padding:0 0.85rem; margin-bottom:12px; background:#2E74B5; color:#ffffff !important;
    font-weight:600; font-size:0.875rem; }

/* profile card = one clickable block that opens the Account page */
.st-key-profilebox { position: relative; }
.st-key-profilebox [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) { position:absolute; inset:0; z-index:5; }
.st-key-profilebox [data-testid="stPageLink-NavLink"] { opacity:0; height:100%; width:100%; }
.profile-card { transition: all .15s ease; }
.st-key-profilebox:hover .profile-card { border-color:#2E74B5; background:#f3f8fd; }
.profile-card.profile-active { background:#e6f1fc; border:2px solid #2E74B5; }

/* metric cards */
[data-testid="stMetric"] {
    background: #ffffff; border: 1px solid #dfe3ea; border-radius: 10px; padding: 0.8rem 1rem;
}
[data-testid="stMetricLabel"] p { font-size: 0.8rem !important; color: #6b7280; }
[data-testid="stMetricValue"] { font-size: 1.35rem !important; }
[data-testid="stMetricValue"] p, [data-testid="stMetricLabel"] p,
[data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"] {
    white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
    overflow-wrap: anywhere; line-height: 1.25; }
/* the dashboard KPI cards drop to a second row when the window is narrow */
.st-key-kpis [data-testid="stHorizontalBlock"] { display: grid !important;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.75rem 1rem; }
.st-key-kpis [data-testid="stColumn"] { width: auto !important; min-width: 0 !important; flex: unset !important; }

/* buttons and inputs */
.stButton > button, .stDownloadButton > button, [data-testid^="stBaseButton"] { border-radius: 8px; font-weight: 600; }
[data-testid="stForm"] { border: 1px solid #dfe3ea; border-radius: 10px; }
</style>
"""

# Dark mode: invert the whole page (so EVERY component - date picker, file uploader, password eye,
# tables, charts - stays readable) and flip photos back so receipts look normal.
DARK_CSS = """
<style>
html { filter: invert(0.92) hue-rotate(180deg); background: #ffffff; }
img, video, [data-testid="stImage"] img { filter: invert(1) hue-rotate(180deg); }
</style>
"""

st.markdown(BASE_CSS, unsafe_allow_html=True)
if st.session_state.get("dark_mode"):
    st.markdown(DARK_CSS, unsafe_allow_html=True)

# ----------------------------------------------------------------------------- dashboard page
def dashboard():
    user = ui.require_login()
    st.title(f"IPECS — {t('Dashboard')}")
    if user["role"] == "admin":
        st.info(t("You are logged in as the administrator. Use the Admin Panel to manage users and system data."))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(t("Total users"), len([u for u in db.list_users() if u["role"] == "user"]))
        c2.metric(t("Total transactions"), db.count_transactions_all())
        c3.metric(t("Receipts uploaded"), db.count_receipts_all())
        c4.metric(t("Active anomaly alerts"), db.count_active_alerts_all())
        st.page_link("pages/9_Admin_Panel.py", label=t("Open Admin Panel"))
        return

    uid = user["id"]
    st.subheader(t("Hello, {name}!", name=user["username"]))
    ui.budget_banner(uid)
    month = analytics.month_str(date.today())
    summary = analytics.monthly_summary(uid, month)
    total = float(summary["total"].sum()) if not summary.empty else 0.0
    all_tx = db.get_transactions(uid)
    top_cat = "—"
    if not summary.empty:                       # most frequent = highest number of transactions
        top_cat = ui.cat_label(summary.sort_values("count", ascending=False).iloc[0]["category_name"])
    bva = analytics.budget_vs_actual(uid, month)
    pct = (bva["actual"].sum() / bva["budget"].sum() * 100) if not bva.empty and bva["budget"].sum() > 0 else None
    active_alerts = db.get_alerts(uid, "active")
    next_month = fc.target_month()
    forecasts = db.get_forecasts(uid, next_month)
    fc_total = sum(f["forecast_amount"] for f in forecasts) if forecasts else None

    with st.container(key="kpis"):
        k = st.columns(6)
        k[0].metric(t("Spent this month"), ui.money(total))
        k[1].metric(t("Transactions recorded"), len(all_tx))
        k[2].metric(t("Most frequent category"), top_cat)
        k[3].metric(t("Budget used"), f"{pct:.0f}%" if pct is not None else "—")
        k[4].metric(t("Unresolved alerts"), len(active_alerts))
        k[5].metric(t("Forecast next month"), ui.money(fc_total) if fc_total is not None else "—")

    if not all_tx:
        st.info(t("No transactions yet. Upload a receipt or add a transaction manually to get started."))
        st.page_link("pages/2_Receipts.py", label=t("Add your first transaction"))

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**{t('Monthly spending trend')}**")
        trend = analytics.monthly_totals(uid, 6)
        fig = px.line(trend, x="month", y="total", markers=True, labels={"month": t("Month"), "total": "RM"})
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.markdown(f"**{t('Category breakdown')} ({month})**")
        if summary.empty:
            st.caption(t("No spending recorded this month."))
        else:
            s2 = summary.copy()
            s2["category_name"] = s2["category_name"].map(ui.cat_label)
            st.plotly_chart(px.pie(s2, names="category_name", values="total", hole=0.35), width="stretch")

    st.markdown(f"**{t('Budget progress')}**")
    if bva.empty:
        st.caption(t("No budget goals set for this month."))
        st.page_link("pages/5_Budget_Goals.py", label=t("Set a budget goal"))
    else:
        b = bva.copy()
        b["category_name"] = b["category_name"].map(ui.cat_label)
        long = pd.melt(b, id_vars="category_name", value_vars=["budget", "actual"], var_name="type", value_name="RM")
        st.plotly_chart(px.bar(long, x="category_name", y="RM", color="type", barmode="group",
                               labels={"category_name": t("Category")}), width="stretch")

    a1, a2 = st.columns(2)
    with a1:
        st.markdown(f"**{t('Anomaly alerts')}**")
        if not active_alerts:
            st.caption(t("No active anomaly alerts."))
        for a in active_alerts[:3]:
            st.warning(f"{a['merchant']} — {ui.money(a['amount'])} ({ui.cat_label(a['category_name'])}), Z = {a['z_score']:.2f}")
        st.page_link("pages/7_Anomaly_Alerts.py", label=t("View all alerts"))
    with a2:
        st.markdown(f"**{t('Forecast preview')} ({next_month})**")
        if not forecasts:
            st.caption(t("No forecast yet. Open the Forecast page and press Recalculate."))
        for f in forecasts[:4]:
            st.write(f"{ui.cat_label(f['category_name'])}: **{ui.money(f['forecast_amount'])}**")
        st.page_link("pages/8_Forecast.py", label=t("Open forecasts"))

    st.markdown(f"**{t('Recent transactions')}**")
    if all_tx:
        recent = pd.DataFrame(all_tx[:8])[["date", "merchant", "category_name", "amount"]]
        recent["category_name"] = recent["category_name"].map(ui.cat_label)
        recent.columns = [t("Date"), t("Merchant"), t("Category"), "RM"]
        st.dataframe(recent, width="stretch", hide_index=True)

    st.markdown(f"**{t('Financial insights')}**")
    for tip in analytics.insight_tips(uid):
        st.write("• " + tip)


# ----------------------------------------------------------------------------- navigation
user = st.session_state.get("user")
account_page = st.Page("pages/1_Account.py", title=t("Account"))
if not user:
    pages = [st.Page("pages/1_Account.py", title=t("Login / Register"))]
else:
    pages = [st.Page(dashboard, title=t("Dashboard"), url_path="dashboard", default=True), account_page]
    if user["role"] == "admin":
        pages.append(st.Page("pages/9_Admin_Panel.py", title=t("Admin Panel")))
    else:
        pages += [st.Page("pages/2_Receipts.py", title=t("Receipts")),
                  st.Page("pages/3_Transactions.py", title=t("Transactions")),
                  st.Page("pages/4_Categories.py", title=t("Categories")),
                  st.Page("pages/5_Budget_Goals.py", title=t("Budget Goals")),
                  st.Page("pages/6_Reports.py", title=t("Reports")),
                  st.Page("pages/7_Anomaly_Alerts.py", title=t("Anomaly Alerts")),
                  st.Page("pages/8_Forecast.py", title=t("Forecast")),
                  st.Page("pages/10_Sync_Status.py", title=t("Sync Status"))]
nav = st.navigation(pages, position="hidden")      # our own sidebar menu is drawn below
if user and st.session_state.pop("_goto_dashboard", False):
    st.switch_page(pages[0])

# ----------------------------------------------------------------------------- sidebar
def nav_item(page, label=None):
    """Current page = solid blue box, other pages = light-blue links."""
    label = label or page.title
    if page.title == nav.title:
        st.markdown(f"<div class='nav-active'>{label}</div>", unsafe_allow_html=True)
    else:
        st.page_link(page, label=label)


with st.sidebar:
    if user:
        initial = user["username"][:1].upper()
        on_account = (nav.title == account_page.title)
        with st.container(key="profilebox"):
            st.markdown(
                f"<div class='profile-card{' profile-active' if on_account else ''}'>"
                f"<div class='profile-avatar'>{initial}</div>"
                f"<div><div class='profile-name'>{user['username']}</div>"
                f"<div class='profile-role'>{user['role']}</div></div></div>", unsafe_allow_html=True)
            st.page_link(account_page, label=t("Account"))
        st.divider()
        for p_ in pages:
            if p_.title != account_page.title:
                nav_item(p_)
        st.divider()
        online = ui.online_status()
        st.markdown((":green[●] " + t("Online")) if online else (":red[●] " + t("Offline")))
        if user["role"] != "admin":
            ui.run_auto_sync(user["id"])
            cloud_mode.push_now(user["id"])          # cloud: save changes to Supabase immediately
            sc = db.sync_counts(user["id"])
            st.caption(t("Sync: {p} pending · {c} conflict(s)", p=sc["pending"], c=sc["conflict"]))
    st.toggle("Dark mode", key="dark_mode")
    st.toggle("Bahasa Malaysia", key="lang_bm")
    if user and st.button(t("Log out"), width="stretch"):
        keep = {k: st.session_state.get(k) for k in ("lang_bm", "dark_mode")}
        st.session_state.clear()
        st.session_state.update(keep)
        st.rerun()

nav.run()
if user and user["role"] != "admin":
    cloud_mode.push_now(user["id"])
