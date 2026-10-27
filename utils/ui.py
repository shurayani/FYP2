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
        st.page_link("views/1_Account.py", label=t("Go to login"))
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



# ---------------------------------------------------------------- look & feel (patch #20)
from html import escape as _esc

CHART_COLORS = ["#0F7B6C", "#2F6DB5", "#D9861C", "#6B46A3", "#C2412D", "#4E9A3A", "#8A94A6"]
try:                                                    # same banknote colours in every Plotly chart
    import plotly.express as _px
    _px.defaults.color_discrete_sequence = CHART_COLORS
except Exception:
    pass

_MONTHS_MS = ["Januari", "Februari", "Mac", "April", "Mei", "Jun", "Julai", "Ogos", "September", "Oktober",
              "November", "Disember"]


def month_label(month: str) -> str:
    """'2026-10' -> 'October 2026' (or 'Oktober 2026' in BM)."""
    try:
        y, m = month.split("-")
        m = int(m)
    except (ValueError, AttributeError):
        return str(month)
    name = _MONTHS_MS[m - 1] if st.session_state.get("lang") == "ms" else date(2000, m, 1).strftime("%B")
    return f"{name} {y}"


def mark_svg(bg="#16253D", size=48) -> str:
    """The IPECS mark: a receipt with a torn edge."""
    return (f"<svg width='{size}' height='{size}' viewBox='0 0 48 48' xmlns='http://www.w3.org/2000/svg' "
            f"aria-hidden='true'><rect width='48' height='48' rx='12' fill='{bg}'/>"
            "<path d='M15 10h18v27l-3-2.5-3 2.5-3-2.5-3 2.5-3-2.5-3 2.5z' fill='#FFFFFF'/>"
            "<path d='M19 16.5h10M19 21h7M19 25.5h10' stroke='#3FB8A4' stroke-width='2.2' "
            "stroke-linecap='round'/></svg>")


def sidebar_brand() -> str:
    return f"<div class='side-brand'>{mark_svg('#0F7B6C', 30)}<span>IPECS</span></div>"


def brand_header() -> str:
    return ("<div class='brand'>" + mark_svg() +
            "<div><div class='brand-name'>IPECS</div>"
            f"<div class='brand-tag'>{_esc(t('Intelligent Personal Expense Categorization System'))}</div></div></div>"
            f"<p class='brand-pitch'>{_esc(t('Snap a receipt and IPECS sorts your spending into categories, tracks your budgets and warns you about unusual expenses.'))}</p>")


def receipt_slip(month_text, lines, total, top_category=None) -> str:
    """This month's spending printed like a receipt. lines = [(category label, amount)]."""
    rows = "".join(f"<div class='slip-line'><span class='slip-item'>{_esc(name)}</span><span class='slip-dots'></span>"
                   f"<span class='slip-amt'>{money(amount)}</span></div>" for name, amount in lines)
    if not rows:
        rows = f"<div class='slip-empty'>{_esc(t('No spending recorded yet this month.'))}</div>"
    foot = (f"<div class='slip-foot'>{_esc(t('Most frequent category: {c}', c=top_category))}</div>"
            if top_category else "")
    return ("<div class='slip-wrap'><div class='slip'>"
            f"<div class='slip-head'><span class='slip-brand'>IPECS</span><span>{_esc(month_text)}</span></div>"
            f"<div class='slip-sub'>{_esc(t('Spending so far this month'))}</div><div class='slip-rule'></div>"
            f"{rows}<div class='slip-rule'></div>"
            f"<div class='slip-total'><span>{_esc(t('Total'))}</span><span>{money(total)}</span></div>{foot}"
            "</div></div>")


def budget_meter(pct) -> str:
    """Budget used this month as a bar: teal, orange from 75 %, red from 100 %."""
    if pct is None:
        return (f"<div class='meter'><div class='meter-top'><span>{_esc(t('Budget used this month'))}</span>"
                f"<b>—</b></div><div class='meter-note'>{_esc(t('No budget goals set for this month.'))}</div></div>")
    colour = "#C2412D" if pct >= 100 else "#D9861C" if pct >= 75 else "#0F7B6C"
    return (f"<div class='meter'><div class='meter-top'><span>{_esc(t('Budget used this month'))}</span>"
            f"<b>{pct:.0f}%</b></div><div class='meter-track'>"
            f"<div class='meter-fill' style='width:{max(0, min(100, pct)):.0f}%;background:{colour}'></div></div></div>")



def bill_reminders(user_id, key_prefix="dash"):
    """Recurring bills that are due: Add / Change amount / Skip (patch #23). Nothing happens automatically."""
    from src import analytics, recurring
    due = recurring.due_bills(user_id)
    if not due:
        return
    st.subheader(t("Bills due"), anchor=False)
    for b in due:
        when = (t("overdue since {d}", d=f"{b['due'].day} {b['due']:%b}") if b["overdue"]
                else t("due {d}", d=f"{b['due'].day} {b['due']:%b}"))
        with st.container(border=True, key=f"{key_prefix}_bill_{b['id']}"):
            c1, c2, c3, c4 = st.columns([3, 1, 1.4, 1], vertical_alignment="center")
            c1.markdown(f"**{b['name']}** · {money(b['amount'])}  \n{cat_label(b['category_name'])} · {when}")
            if c2.button(t("Add"), key=f"{key_prefix}_add_{b['id']}", type="primary"):
                recurring.confirm(b, user_id)
                analytics.detect_anomalies(user_id)
                st.rerun()
            with c3.popover(t("Change amount")):
                new_amt = money_input(t("This month's amount"), value=float(b["amount"]),
                                      key=f"{key_prefix}_amt_{b['id']}")
                keep = st.checkbox(t("Use this amount from now on"), key=f"{key_prefix}_keep_{b['id']}")
                if st.button(t("Add with this amount"), key=f"{key_prefix}_addamt_{b['id']}") and new_amt > 0:
                    recurring.confirm(b, user_id, amount=new_amt, keep_amount=keep)
                    analytics.detect_anomalies(user_id)
                    st.rerun()
            if c4.button(t("Skip"), key=f"{key_prefix}_skip_{b['id']}"):
                recurring.skip(b, user_id)
                st.rerun()
