"""One-time patch #2:
  * sidebar: current page highlighted, Account moved under the profile card
  * dashboard: 'Quick navigation' removed
  * forecast: works with 3 WEEKS of history (weekly short-history mode), monthly Prophet kept for 3+ months
Run once from the project folder:   python patch_v2.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NAV_MARK = "# ----------------------------------------------------------------------------- navigation"
SIDE_MARK = "# ----------------------------------------------------------------------------- sidebar"

# ============================================================ app.py
p = ROOT / "app.py"
s = p.read_text(encoding="utf-8")
if "nav-active" in s:
    print("app.py already patched")
else:
    # 1) remove Quick navigation block
    a = s.index("    st.markdown(f\"**{t('Quick navigation')}**\")")
    b = s.index(NAV_MARK)
    s = s[:a].rstrip() + "\n\n\n" + s[b:]

    # 2) css for the active menu box
    css = """.nav-active { border:1px solid #2E74B5; border-radius:8px; padding:0.5rem 0.85rem; margin-bottom:4px;
    background:#2E74B5; color:#ffffff !important; font-weight:600; font-size:0.9rem; line-height:1.6; }
"""
    s = s.replace("/* metric cards */", css + "\n/* metric cards */", 1)
    s = s.replace("padding:0.8rem 0.9rem; margin-bottom:0.9rem;", "padding:0.8rem 0.9rem; margin-bottom:0.5rem;")

    # 3) navigation block (Account page stays registered but is drawn under the profile card)
    a = s.index(NAV_MARK)
    b = s.index(SIDE_MARK)
    nav_block = NAV_MARK + '''
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

'''
    s = s[:a] + nav_block + s[b:]

    # 4) sidebar block
    a = s.index(SIDE_MARK)
    b = s.index("nav.run()")
    sidebar = SIDE_MARK + '''
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
        st.markdown(
            f"<div class='profile-card'><div class='profile-avatar'>{initial}</div>"
            f"<div><div class='profile-name'>{user['username']}</div>"
            f"<div class='profile-role'>{user['role']}</div></div></div>", unsafe_allow_html=True)
        nav_item(account_page, t("Account"))
        st.divider()
        for p_ in pages:
            if p_.title != account_page.title:
                nav_item(p_)
        st.divider()
        online = ui.online_status()
        st.markdown((":green[●] " + t("Online")) if online else (":red[●] " + t("Offline")))
        if user["role"] != "admin":
            ui.run_auto_sync(user["id"])
            sc = db.sync_counts(user["id"])
            st.caption(t("Sync: {p} pending · {c} conflict(s)", p=sc["pending"], c=sc["conflict"]))
    st.toggle("Dark mode", key="dark_mode")
    st.toggle("Bahasa Malaysia", key="lang_bm")
    if user and st.button(t("Log out"), width="stretch"):
        keep = {k: st.session_state.get(k) for k in ("lang_bm", "dark_mode")}
        st.session_state.clear()
        st.session_state.update(keep)
        st.rerun()

'''
    s = s[:a] + sidebar + s[b:]
    p.write_text(s, encoding="utf-8")
    print("app.py patched")

# ============================================================ utils/config.py
p = ROOT / "utils" / "config.py"
s = p.read_text(encoding="utf-8")
if "MIN_WEEKS_FOR_FORECAST" not in s:
    s += "MIN_WEEKS_FOR_FORECAST = 3          # short-history mode: weekly Prophet when < 3 months of data\n"
    p.write_text(s, encoding="utf-8")
    print("config.py patched")

# ============================================================ utils/i18n.py (new strings)
p = ROOT / "utils" / "i18n.py"
s = p.read_text(encoding="utf-8")
if "short-history" not in s:
    s += '''

MS.update({
    "Next-month forecasts per category are computed offline with Prophet. Needs {m} months of history, or {w} weeks for a lower-accuracy short-history estimate.":
        "Ramalan bulan depan bagi setiap kategori dikira secara luar talian dengan Prophet. Perlukan {m} bulan sejarah, atau {w} minggu untuk anggaran sejarah pendek yang kurang tepat.",
    "Not enough history to forecast yet. Record transactions across at least {w} weeks.":
        "Sejarah belum mencukupi untuk meramal. Rekod transaksi merentasi sekurang-kurangnya {w} minggu.",
})
'''
    p.write_text(s, encoding="utf-8")
    print("i18n.py patched")

# ============================================================ pages/8_Forecast.py
p = ROOT / "pages" / "8_Forecast.py"
s = p.read_text(encoding="utf-8")
if "MIN_WEEKS_FOR_FORECAST" not in s:
    s = s.replace("from utils.config import MIN_MONTHS_FOR_FORECAST",
                  "from utils.config import MIN_MONTHS_FOR_FORECAST, MIN_WEEKS_FOR_FORECAST")
    a = s.index('st.caption(t("Next-month forecasts')
    b = s.index("if st.button(t(\"Recalculate forecasts\")")
    s = s[:a] + ('st.caption(t("Next-month forecasts per category are computed offline with Prophet. Needs {m} months of history, '
                 'or {w} weeks for a lower-accuracy short-history estimate.",\n'
                 '             m=MIN_MONTHS_FOR_FORECAST, w=MIN_WEEKS_FOR_FORECAST))\n\n') + s[b:]
    a = s.index('st.warning(t("Not enough history')
    b = s.index("\n", a)
    s = s[:a] + 'st.warning(t("Not enough history to forecast yet. Record transactions across at least {w} weeks.", w=MIN_WEEKS_FOR_FORECAST))' + s[b:]
    p.write_text(s, encoding="utf-8")
    print("8_Forecast.py patched")

# ============================================================ src/forecast.py (full replacement)
p = ROOT / "src" / "forecast.py"
p.write_text('''"""Spending forecast (Module 8, FR11, Section 5.6.8).

Primary layer : Prophet, fully offline - next-month forecast per category with confidence interval.
    * normal mode        : >= 3 complete months of history -> monthly Prophet (as in the report)
    * short-history mode : < 3 months but >= 3 complete weeks -> weekly Prophet, scaled to one month
                           (lower accuracy; lets the system be demonstrated early)
Secondary layer: optional Gemini insights (utils/gemini_helper) when online; skipped silently otherwise."""
import logging
from datetime import date, timedelta

import pandas as pd

from src import analytics, db_manager as db
from utils import gemini_helper
from utils.config import MIN_MONTHS_FOR_FORECAST, MIN_WEEKS_FOR_FORECAST

logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)


def target_month() -> str:
    """The forecast target is the calendar month after the current one."""
    return analytics.add_months(analytics.month_str(date.today()), 1)


def _category_monthly(df: pd.DataFrame, category_id: str, last_complete: str) -> pd.DataFrame:
    d = df[(df["category_id"] == category_id) & (df["date"].dt.strftime("%Y-%m") <= last_complete)].copy()
    if d.empty:
        return pd.DataFrame(columns=["ds", "y"])
    d["m"] = d["date"].dt.to_period("M")
    g = d.groupby("m")["amount"].sum()
    full = pd.period_range(g.index.min(), pd.Period(last_complete), freq="M")
    g = g.reindex(full, fill_value=0.0)
    return pd.DataFrame({"ds": g.index.to_timestamp(), "y": g.values})


def _category_weekly(df: pd.DataFrame, category_id: str) -> pd.DataFrame:
    """Weekly totals (Mon-Sun) for complete weeks only; missing weeks count as 0."""
    week_start = pd.Timestamp(date.today() - timedelta(days=date.today().weekday()))
    d = df[(df["category_id"] == category_id) & (df["date"] < week_start)].copy()
    if d.empty:
        return pd.DataFrame(columns=["ds", "y"])
    d["w"] = d["date"].dt.to_period("W-SUN")
    g = d.groupby("w")["amount"].sum()
    full = pd.period_range(g.index.min(), pd.Period(week_start - pd.Timedelta(days=1), freq="W-SUN"), freq="W-SUN")
    g = g.reindex(full, fill_value=0.0)
    out = pd.DataFrame({"ds": g.index.start_time, "y": g.values})
    # the very first week is usually only partly covered -> it would fake an upward trend, so drop it
    first_day = df["date"].min()
    first_week = first_day.to_period("W-SUN").start_time
    if len(out) > MIN_WEEKS_FOR_FORECAST and out["ds"].iloc[0] == first_week and first_day > first_week:
        out = out.iloc[1:].reset_index(drop=True)
    return out


def prophet_forecast(series: pd.DataFrame, periods: int):
    """Fit Prophet on monthly totals and return (yhat, lower, upper) for the last future month."""
    from prophet import Prophet
    logging.getLogger("cmdstanpy").setLevel(logging.WARNING)     # silence per-fit INFO chatter
    m = Prophet(yearly_seasonality=False, weekly_seasonality=False, daily_seasonality=False,
                interval_width=0.8)
    m.fit(series)
    future = m.make_future_dataframe(periods=periods, freq="MS")
    fc = m.predict(future).iloc[-1]
    return max(0.0, float(fc["yhat"])), max(0.0, float(fc["yhat_lower"])), max(0.0, float(fc["yhat_upper"]))


def prophet_forecast_weekly(series: pd.DataFrame, target: str):
    """Short-history mode: fit weekly totals, average the next 4 weeks and scale to the target month.
    growth='flat' (no trend) because a trend cannot be estimated reliably from a few weeks."""
    from prophet import Prophet
    logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
    m = Prophet(growth="flat", yearly_seasonality=False, weekly_seasonality=False, daily_seasonality=False,
                interval_width=0.8)
    m.fit(series)
    future = m.make_future_dataframe(periods=4, freq="7D")
    fc = m.predict(future).tail(4)
    days = pd.Period(target).days_in_month
    scale = days / 7.0
    return (max(0.0, float(fc["yhat"].mean()) * scale),
            max(0.0, float(fc["yhat_lower"].mean()) * scale),
            max(0.0, float(fc["yhat_upper"].mean()) * scale))


def generate_forecasts(user_id) -> dict:
    """(Re)calculate next-month forecasts for every category with enough history and save them.
    Returns {"saved": n, "skipped": [category names], "short_history": [category names], "target": month}."""
    df = analytics.transactions_df(user_id)
    target = target_month()
    saved, skipped, short = 0, [], []
    if df.empty:
        return {"saved": 0, "skipped": [], "short_history": [], "target": target}
    last_complete = analytics.add_months(analytics.month_str(date.today()), -1)
    for _, cat in df[["category_id", "category_name"]].drop_duplicates().iterrows():
        monthly = _category_monthly(df, cat["category_id"], last_complete)
        if len(monthly) >= MIN_MONTHS_FOR_FORECAST and monthly["y"].sum() > 0:
            yhat, lo, hi = prophet_forecast(monthly, 2)       # last complete month -> this month -> target
        else:
            weekly = _category_weekly(df, cat["category_id"])
            if len(weekly) < MIN_WEEKS_FOR_FORECAST or weekly["y"].sum() <= 0:
                skipped.append(cat["category_name"])
                continue
            yhat, lo, hi = prophet_forecast_weekly(weekly, target)
            short.append(cat["category_name"])
        db.save_forecast(user_id, cat["category_id"], target, yhat, lo, hi)
        saved += 1
    return {"saved": saved, "skipped": skipped, "short_history": short, "target": target}


def forecast_summary(user_id, month: str) -> dict:
    """Structured summary sent to Gemini for insights."""
    f = db.get_forecasts(user_id, month)
    cur = analytics.monthly_summary(user_id, analytics.month_str(date.today()))
    budgets = db.get_budgets(user_id, month)
    return {
        "forecast_month": month,
        "forecasts": [{"category": x["category_name"], "forecast": round(x["forecast_amount"], 2),
                       "low": round(x["confidence_lower"] or 0, 2), "high": round(x["confidence_upper"] or 0, 2)}
                      for x in f],
        "current_month_actual": [{"category": r["category_name"], "total": round(float(r["total"]), 2)}
                                 for _, r in cur.iterrows()],
        "budgets": [{"category": b["category_name"], "amount": b["budget_amount"]} for b in budgets],
    }


def get_ai_insights(user_id, month: str, language: str = "English"):
    """Optional layer. Returns text, or None if offline / no key / request fails (silent skip)."""
    from src.ocr_module import is_online
    if not gemini_helper.is_configured() or not is_online():
        return None
    try:
        return gemini_helper.generate_insights(forecast_summary(user_id, month), language)
    except Exception:
        return None
''', encoding="utf-8")
print("forecast.py replaced")
print("Done. Restart Streamlit.")