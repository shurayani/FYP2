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
if cloud_mode.ready() and cloud_mode.local_user_count() == 0:       # cloud database empty -> pull it back
    with st.spinner("Loading saved accounts and transactions..."):
        _restored = cloud_mode.restore_if_empty()
    if _restored and _restored.get("error"):
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
h1 { letter-spacing: -0.02em; }
h2, h3 { letter-spacing: -0.01em; }

/* ---------- sidebar (its colours come from [theme.sidebar] in .streamlit/config.toml) */
.side-brand { display:flex; align-items:center; gap:10px; margin:0 0 1rem 2px; }
.side-brand svg { flex:none; }
.side-brand span { font-family:"Bricolage Grotesque", sans-serif; font-weight:800; font-size:1.25rem;
    color:#F4F7F6; letter-spacing:-0.01em; }
.profile-card { display:flex; align-items:center; gap:12px; padding:0.7rem 0.8rem; margin-bottom:0.25rem;
    background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.12); border-radius:12px;
    transition:background .15s ease, border-color .15s ease; }
.profile-avatar { width:38px; height:38px; border-radius:50%; background:#3FB8A4; color:#16253D; flex:none;
    display:flex; align-items:center; justify-content:center; font-weight:800; font-size:1rem;
    font-family:"Bricolage Grotesque", sans-serif; }
.profile-name { font-weight:650; line-height:1.2; color:#F4F7F6; }
.profile-role { font-size:0.78rem; color:#9FB2C4; }
.profile-role::first-letter { text-transform:uppercase; }
.st-key-profilebox { position:relative; }
.st-key-profilebox [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) { position:absolute; inset:0; z-index:5; }
.st-key-profilebox [data-testid="stPageLink-NavLink"] { opacity:0; height:100%; width:100%; }
.st-key-profilebox:hover .profile-card { background:rgba(255,255,255,0.1); border-color:rgba(63,184,164,0.6); }
.profile-card.profile-active { background:rgba(63,184,164,0.14); border-color:#3FB8A4; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] { border:0; border-radius:8px; padding:0.45rem 0.75rem;
    margin-bottom:2px; background:transparent; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p { color:#C9D5DF; font-weight:500; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover { background:rgba(255,255,255,0.07); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover p { color:#FFFFFF; }
.nav-active { box-sizing:border-box; display:flex; align-items:center; min-height:38px; border-radius:8px;
    padding:0 0.75rem; margin:2px 0 6px; background:#0F7B6C; color:#FFFFFF !important; font-weight:600;
    font-size:0.875rem; box-shadow:inset 3px 0 0 #3FB8A4; }
[data-testid="stSidebar"] hr { border-color:rgba(255,255,255,0.1); margin:0.8rem 0; }

/* ---------- metrics and forms */
[data-testid="stMetric"] { background:#FFFFFF; border:1px solid #D3DCDA; border-radius:12px; padding:0.85rem 1rem; }
[data-testid="stMetricLabel"] p { font-size:0.82rem !important; color:#5B6B7F; }
[data-testid="stMetricValue"] { font-family:"Bricolage Grotesque", sans-serif; font-size:1.45rem !important;
    font-weight:700; color:#16253D; }
[data-testid="stMetricValue"] p, [data-testid="stMetricLabel"] p,
[data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"] {
    white-space:normal !important; overflow:visible !important; text-overflow:clip !important;
    overflow-wrap:anywhere; line-height:1.25; }
.st-key-glance [data-testid="stHorizontalBlock"] { display:grid !important;
    grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:0.75rem; }
.st-key-glance [data-testid="stColumn"] { width:auto !important; min-width:0 !important; flex:unset !important; }
[data-testid="stForm"] { background:#FFFFFF; border:1px solid #D3DCDA; border-radius:14px; padding:1.1rem 1.2rem; }
.stButton > button, .stDownloadButton > button, [data-testid^="stBaseButton"] { font-weight:600; }

/* ---------- dashboard quick actions */
.st-key-quick_actions [data-testid="stPageLink-NavLink"] { background:#FFFFFF; border:1px solid #D3DCDA;
    border-radius:10px; padding:0.45rem 0.9rem; }
.st-key-quick_actions [data-testid="stPageLink-NavLink"]:hover { border-color:#0F7B6C; }
.st-key-qa_scan [data-testid="stPageLink-NavLink"] { background:#0F7B6C; border-color:#0F7B6C; }
.st-key-qa_scan [data-testid="stPageLink-NavLink"]:hover { background:#0C6559; }
.st-key-qa_scan [data-testid="stPageLink-NavLink"] p, .st-key-qa_scan [data-testid="stPageLink-NavLink"] span { color:#FFFFFF !important; }

/* ---------- this month's receipt (dashboard) */
.slip-wrap { filter:drop-shadow(0 1px 0 #D3DCDA) drop-shadow(0 10px 16px rgba(22,37,61,0.08)); margin-bottom:1rem; }
.slip { --z:9px; background:#FFFFFF; padding:1.25rem 1.4rem calc(1.25rem + var(--z)); color:#16253D;
    font-family:"IBM Plex Mono", ui-monospace, monospace; font-size:0.9rem;
    -webkit-mask:conic-gradient(from -45deg at bottom, #0000, #000 1deg 89deg, #0000 90deg) 50% / calc(2 * var(--z)) 100%;
            mask:conic-gradient(from -45deg at bottom, #0000, #000 1deg 89deg, #0000 90deg) 50% / calc(2 * var(--z)) 100%; }
.slip-head { display:flex; justify-content:space-between; align-items:baseline; gap:1rem; font-weight:600; }
.slip-brand { font-family:"Bricolage Grotesque", sans-serif; font-weight:800; font-size:1.15rem; }
.slip-sub { color:#5B6B7F; font-size:0.8rem; margin-top:2px; }
.slip-rule { border-top:1.5px dashed #AEBBC0; margin:0.8rem 0; }
.slip-line { display:flex; align-items:baseline; gap:6px; padding:3px 0; }
.slip-item { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:62%; }
.slip-dots { flex:1; min-width:12px; border-bottom:1.5px dotted #C5CFD2; transform:translateY(-4px); }
.slip-amt { white-space:nowrap; font-variant-numeric:tabular-nums; }
.slip-total { display:flex; justify-content:space-between; align-items:baseline; gap:1rem; font-weight:700; }
.slip-total span:last-child { font-family:"Bricolage Grotesque", sans-serif; font-size:2.1rem; line-height:1.1;
    letter-spacing:-0.02em; color:#0F7B6C; }
.slip-foot { margin-top:0.6rem; font-size:0.8rem; color:#5B6B7F; }
.slip-empty { color:#5B6B7F; padding:0.3rem 0; }
.meter { background:#FFFFFF; border:1px solid #D3DCDA; border-radius:12px; padding:0.85rem 1rem; margin-bottom:0.75rem; }
.meter-top { display:flex; justify-content:space-between; align-items:baseline; font-size:0.82rem; color:#5B6B7F; }
.meter-top b { font-family:"Bricolage Grotesque", sans-serif; font-size:1.45rem; color:#16253D; }
.meter-track { height:10px; background:#E3E9E7; border-radius:99px; margin-top:0.5rem; overflow:hidden; }
.meter-fill { height:100%; border-radius:99px; }
.meter-note { font-size:0.82rem; color:#5B6B7F; margin-top:0.3rem; }

/* ---------- login page */
.brand { display:flex; align-items:center; gap:14px; margin:0.5rem 0 0.6rem; }
.brand svg { flex:none; }
.brand-name { font-family:"Bricolage Grotesque", sans-serif; font-weight:800; font-size:2.5rem; line-height:1;
    letter-spacing:-0.03em; color:#16253D; }
.brand-tag { color:#5B6B7F; font-size:0.9rem; margin-top:4px; }
.brand-pitch { font-size:1.02rem; line-height:1.55; color:#2A3A52; max-width:34rem; margin:0.4rem 0 1rem; }
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
    if user["role"] == "admin":
        users = [u for u in db.list_users() if u["role"] == "user"]
        head_l, head_r = st.columns([3, 2], vertical_alignment="bottom")
        with head_l:
            st.title(t("Dashboard"), anchor=False)
            st.caption(t("System overview for the administrator."))
        with head_r:
            with st.container(key="quick_actions", horizontal=True, horizontal_alignment="right"):
                with st.container(key="qa_scan"):
                    st.page_link("views/9_Admin_Panel.py", label=t("Open Admin Panel"),
                                 icon=":material/admin_panel_settings:")
        with st.container(key="glance"):
            k = st.columns(4)
            k[0].metric(t("Total users"), len(users))
            k[1].metric(t("Total transactions"), db.count_transactions_all())
            k[2].metric(t("Receipts uploaded"), db.count_receipts_all())
            k[3].metric(t("Active anomaly alerts"), db.count_active_alerts_all())

        acc = db.classifier_accuracy()
        st.subheader(t("Category suggestions in real use"), anchor=False)
        if not acc["total"]:
            st.caption(t("No data yet. This fills in as users save transactions with the category IPECS suggested."))
        else:
            a1, a2 = st.columns([1, 2], gap="large")
            a1.metric(t("Suggestions kept by users"), f"{acc['kept'] / acc['total'] * 100:.0f}%")
            a1.caption(t("{k} of {n} suggested categories were kept.", k=acc["kept"], n=acc["total"]))
            with a2:
                if acc["corrections"]:
                    st.caption(t("Most common corrections"))
                    st.dataframe(pd.DataFrame({
                        t("Suggested"): [ui.cat_label(c_["suggested"]) for c_ in acc["corrections"]],
                        t("Changed to"): [ui.cat_label(c_["chosen"]) for c_ in acc["corrections"]],
                        t("Times"): [c_["times"] for c_ in acc["corrections"]]}), width="stretch", hide_index=True)
                else:
                    st.caption(t("No suggestion has been corrected so far."))

        c1, c2 = st.columns([3, 2], gap="large")
        with c1:
            st.subheader(t("Activity per month"), anchor=False)
            tx_m, rc_m = db.activity_by_month()
            cur = analytics.month_str(date.today())
            months = [analytics.add_months(cur, -i) for i in range(5, -1, -1)]
            act = pd.DataFrame({"month": [ui.month_label(m) for m in months] * 2,
                                "count": [tx_m.get(m, 0) for m in months] + [rc_m.get(m, 0) for m in months],
                                "type": [t("Transactions")] * 6 + [t("Receipts")] * 6})
            fig = px.bar(act, x="month", y="count", color="type", barmode="group",
                         labels={"month": "", "count": "", "type": ""})
            fig.update_layout(legend=dict(orientation="h", y=1.12), margin=dict(t=10))
            st.plotly_chart(fig, width="stretch")
        with c2:
            st.subheader(t("How receipts were read"), anchor=False)
            eng = db.ocr_engine_counts()
            if not eng:
                st.caption(t("No receipts uploaded yet."))
            else:
                names = {"gemini": "Gemini AI", "paddleocr": "PaddleOCR"}
                pie = pd.DataFrame({"engine": [names.get(k_, k_) for k_ in eng], "n": list(eng.values())})
                fig = px.pie(pie, names="engine", values="n", hole=0.55)
                fig.update_layout(legend=dict(orientation="h", y=-0.1), margin=dict(t=10))
                st.plotly_chart(fig, width="stretch")

        c3, c4 = st.columns(2, gap="large")
        with c3:
            st.subheader(t("Newest users"), anchor=False)
            newest = sorted(users, key=lambda u: u["created_at"] or "", reverse=True)[:5]
            if newest:
                st.dataframe(pd.DataFrame({
                    t("Username"): [u["username"] for u in newest],
                    t("Registered"): [ui.local_time(u["created_at"], False) for u in newest],
                    t("Transactions"): [u["tx_count"] for u in newest],
                    t("Status"): [t("Active") if u["is_active"] else t("Deactivated") for u in newest]}),
                    width="stretch", hide_index=True)
            else:
                st.caption(t("No users found."))
        with c4:
            st.subheader(t("Latest anomaly alerts"), anchor=False)
            alerts = db.recent_alerts_all(5)
            if not alerts:
                st.caption(t("No active anomaly alerts."))
            for a_ in alerts:
                st.warning(f"{a_['username']} · {a_['merchant']} — {ui.money(a_['amount'])} "
                           f"({ui.cat_label(a_['category_name'])}), Z = {a_['z_score']:.2f}")
        return

    uid = user["id"]
    month = analytics.month_str(date.today())
    summary = analytics.monthly_summary(uid, month)
    total = float(summary["total"].sum()) if not summary.empty else 0.0
    all_tx = db.get_transactions(uid)
    top_cat = None
    if not summary.empty:                       # most frequent = highest number of transactions
        top_cat = ui.cat_label(summary.sort_values("count", ascending=False).iloc[0]["category_name"])
    bva = analytics.budget_vs_actual(uid, month)
    pct = (bva["actual"].sum() / bva["budget"].sum() * 100) if not bva.empty and bva["budget"].sum() > 0 else None
    active_alerts = db.get_alerts(uid, "active")
    next_month = fc.target_month()
    forecasts = db.get_forecasts(uid, next_month)
    fc_total = sum(f["forecast_amount"] for f in forecasts) if forecasts else None

    head_l, head_r = st.columns([3, 2], vertical_alignment="bottom")
    with head_l:
        st.title(t("Hello, {name}!", name=user["username"]), anchor=False)
        st.caption(t("Here is where your money went in {m}.", m=ui.month_label(month)))
    with head_r:
        with st.container(key="quick_actions", horizontal=True, horizontal_alignment="right"):
            with st.container(key="qa_scan"):
                st.page_link("views/2_Receipts.py", label=t("Scan a receipt"), icon=":material/photo_camera:")
            with st.container(key="qa_all"):
                st.page_link("views/3_Transactions.py", label=t("All transactions"), icon=":material/receipt_long:")
    ui.budget_banner(uid)
    ui.bill_reminders(uid, "dash")

    slip_col, glance_col = st.columns([5, 4], gap="large")
    with slip_col:
        lines = []
        if not summary.empty:
            by_total = summary.sort_values("total", ascending=False)
            lines = [(ui.cat_label(r["category_name"]), float(r["total"])) for _, r in by_total.head(5).iterrows()]
            rest = float(by_total["total"].iloc[5:].sum())
            if rest > 0:
                lines.append((t("Other categories"), rest))
        st.markdown(ui.receipt_slip(ui.month_label(month), lines, total, top_cat), unsafe_allow_html=True)
    with glance_col:
        st.markdown(ui.budget_meter(pct), unsafe_allow_html=True)
        with st.container(key="glance"):
            g = st.columns(3)
            g[0].metric(t("Unresolved alerts"), len(active_alerts))
            g[1].metric(t("Transactions recorded"), len(all_tx))
            g[2].metric(t("Forecast next month"), ui.money(fc_total) if fc_total is not None else "—")

    if not all_tx:
        st.info(t("No transactions yet. Upload a receipt or add a transaction manually to get started."))
        st.page_link("views/2_Receipts.py", label=t("Add your first transaction"))

    c1, c2 = st.columns(2)
    with c1:
        st.subheader(f"{t('Monthly spending trend')}", anchor=False)
        trend = analytics.monthly_totals(uid, 6)
        fig = px.line(trend, x="month", y="total", markers=True, labels={"month": t("Month"), "total": "RM"})
        st.plotly_chart(fig, width="stretch")
    with c2:
        st.subheader(f"{t('Category breakdown')} ({month})", anchor=False)
        if summary.empty:
            st.caption(t("No spending recorded this month."))
        else:
            s2 = summary.copy()
            s2["category_name"] = s2["category_name"].map(ui.cat_label)
            st.plotly_chart(px.pie(s2, names="category_name", values="total", hole=0.35), width="stretch")

    st.subheader(f"{t('Budget progress')}", anchor=False)
    if bva.empty:
        st.caption(t("No budget goals set for this month."))
        st.page_link("views/5_Budget_Goals.py", label=t("Set a budget goal"))
    else:
        b = bva.copy()
        b["category_name"] = b["category_name"].map(ui.cat_label)
        long = pd.melt(b, id_vars="category_name", value_vars=["budget", "actual"], var_name="type", value_name="RM")
        st.plotly_chart(px.bar(long, x="category_name", y="RM", color="type", barmode="group",
                               labels={"category_name": t("Category")}), width="stretch")

    a1, a2 = st.columns(2)
    with a1:
        st.subheader(f"{t('Anomaly alerts')}", anchor=False)
        if not active_alerts:
            st.caption(t("No active anomaly alerts."))
        for a in active_alerts[:3]:
            st.warning(f"{a['merchant']} — {ui.money(a['amount'])} ({ui.cat_label(a['category_name'])}), Z = {a['z_score']:.2f}")
        st.page_link("views/7_Anomaly_Alerts.py", label=t("View all alerts"))
    with a2:
        st.subheader(f"{t('Forecast preview')} ({next_month})", anchor=False)
        if not forecasts:
            st.caption(t("No forecast yet. Open the Forecast page and press Recalculate."))
        for f in forecasts[:4]:
            st.write(f"{ui.cat_label(f['category_name'])}: **{ui.money(f['forecast_amount'])}**")
        st.page_link("views/8_Forecast.py", label=t("Open forecasts"))

    st.subheader(f"{t('Recent transactions')}", anchor=False)
    if all_tx:
        recent = pd.DataFrame(all_tx[:8])[["date", "merchant", "category_name", "amount"]]
        recent["category_name"] = recent["category_name"].map(ui.cat_label)
        recent.columns = [t("Date"), t("Merchant"), t("Category"), "RM"]
        st.dataframe(recent, width="stretch", hide_index=True)

    st.subheader(f"{t('Financial insights')}", anchor=False)
    for tip in analytics.insight_tips(uid):
        st.write("• " + tip)


# ----------------------------------------------------------------------------- navigation
user = st.session_state.get("user")
account_page = st.Page("views/1_Account.py", title=t("Account"))
if not user:
    pages = [st.Page("views/1_Account.py", title=t("Login / Register"))]
else:
    pages = [st.Page(dashboard, title=t("Dashboard"), url_path="dashboard", default=True), account_page]
    if user["role"] == "admin":
        pages.append(st.Page("views/9_Admin_Panel.py", title=t("Admin Panel")))
    else:
        pages += [st.Page("views/2_Receipts.py", title=t("Receipts")),
                  st.Page("views/3_Transactions.py", title=t("Transactions")),
                  st.Page("views/11_Price_Check.py", title=t("Price Check")),
                  st.Page("views/4_Categories.py", title=t("Categories")),
                  st.Page("views/5_Budget_Goals.py", title=t("Budget Goals")),
                  st.Page("views/12_Recurring_Bills.py", title=t("Recurring Bills")),
                  st.Page("views/6_Reports.py", title=t("Reports")),
                  st.Page("views/7_Anomaly_Alerts.py", title=t("Anomaly Alerts")),
                  st.Page("views/8_Forecast.py", title=t("Forecast")),
                  st.Page("views/10_Sync_Status.py", title=t("Sync Status"))]
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
    st.markdown(ui.sidebar_brand(), unsafe_allow_html=True)
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
