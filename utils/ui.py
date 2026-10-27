"""Small shared Streamlit helpers (login guard, formatting, sidebar, auto-sync)."""
import time
from datetime import date, datetime, timezone

from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from src import db_manager as db
from utils.i18n import t


def current_user():
    return st.session_state.get("user")


def require_login(admin_only: bool = False):
    """Redirect un-authenticated visitors to the login screen; enforce the admin role (NFR09)."""
    user = current_user()
    if not user:
        st.warning(t("Please log in to continue."))
        st.page_link("pages/1_Account.py", label=t("Go to login"))
        st.stop()
    if admin_only and user.get("role") != "admin":
        st.error(t("Access denied. This page is only available to the administrator."))
        st.stop()
    return user


def money(x) -> str:
    try:
        return f"RM {float(x):,.2f}"
    except (TypeError, ValueError):
        return "RM 0.00"


def cat_label(name: str) -> str:
    """Translate the seven system category names; custom names are shown as typed."""
    return t(name)


def category_map(user_id):
    """{display label: category_id} for the user's selectable categories."""
    return {cat_label(c["category_name"]): c["id"] for c in db.get_categories(user_id)}


def progress_bar(pct: float, colour: str) -> str:
    w = max(0, min(100, pct))
    return (f"<div style='background:#e6e6e6;border-radius:8px;height:14px;width:100%'>"
            f"<div style='background:{colour};width:{w:.0f}%;height:14px;border-radius:8px'></div></div>")


def online_status(max_age: int = 30) -> bool:
    """Connectivity check cached for a short time so every rerun does not block on the network."""
    from src.ocr_module import is_online
    last = st.session_state.get("_online_checked", 0)
    if time.time() - last > max_age or "_online" not in st.session_state:
        st.session_state["_online"] = is_online(1.5)
        st.session_state["_online_checked"] = time.time()
    return st.session_state["_online"]


def run_auto_sync(user_id):
    """Sync once per session at login (FR16/FR17) when Supabase is configured and reachable."""
    from src import sync_manager
    if st.session_state.get("_auto_synced") or not sync_manager.is_configured():
        return
    st.session_state["_auto_synced"] = True
    if online_status():
        st.session_state["last_sync_result"] = sync_manager.sync_now(user_id)


def month_options(n_back: int = 12, n_forward: int = 1):
    from src import analytics
    cur = analytics.month_str(date.today())
    return [analytics.add_months(cur, i) for i in range(n_forward, -n_back - 1, -1)]


def page_header(title: str, caption: str = ""):
    st.title(title)
    if caption:
        st.caption(caption)


# ---------------------------------------------------------------- bank-style amount input
_MONEY_DIR = Path(__file__).resolve().parent.parent / "components" / "money_input"
_money_component = (components.declare_component("money_input", path=str(_MONEY_DIR))
                    if (_MONEY_DIR / "index.html").exists() else None)


def money_input(label, value=0.0, key=None, disabled=False):
    """Amount input that works like a bank app: starts at 0.00 and each digit pushes the value up from the sen
    (1 -> 0.01, 12 -> 0.12, 125 -> 1.25). Returns a float in RM with 2 decimals.
    The value is sent to Python when you press Enter or leave the field.
    `value` is only the STARTING amount (use a new `key` to start over). Falls back to st.number_input
    if the component folder is missing."""
    value = round(float(value or 0.0), 2)
    if _money_component is None:
        return float(st.number_input(label, min_value=0.0, value=value, step=0.10, format="%.2f", key=key))
    out = _money_component(label=label, value=value, disabled=disabled, key=key, default=value)
    try:
        return round(max(float(out), 0.0), 2)
    except (TypeError, ValueError):
        return value


def local_time(ts, with_time=True):
    """UTC ISO timestamp (as stored in the database) -> this computer's local time, e.g. '19 Oct 2026, 5:43 PM'."""
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone()
        day = f"{dt.day} {dt:%b %Y}"
        return f"{day}, {dt.hour % 12 or 12}:{dt:%M} {dt:%p}" if with_time else day
    except (ValueError, TypeError):
        return str(ts)


def budget_banner(user_id):
    """Red banner for categories over this month's budget (>= 100 %), amber for >= 75 %."""
    from src import analytics
    bva = analytics.budget_vs_actual(user_id, analytics.month_str(date.today()))
    if bva.empty:
        return

    def lines(df):
        return "; ".join(f"{cat_label(r['category_name'])} (RM {r['actual']:,.2f} / RM {r['budget']:,.2f})"
                         for _, r in df.iterrows())

    over = bva[bva["pct"] >= 100]
    near = bva[(bva["pct"] >= 75) & (bva["pct"] < 100)]
    if not over.empty:
        st.error(t("Over budget this month: {items}", items=lines(over)))
    if not near.empty:
        st.warning(t("Close to the budget limit (75% or more): {items}", items=lines(near)))
