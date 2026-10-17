"""Small shared Streamlit helpers (login guard, formatting, sidebar, auto-sync)."""
import time
from datetime import date

import streamlit as st

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
