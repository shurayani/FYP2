"""One-time patch #12:
  1. Metric values and labels (e.g. 'Last sync') wrap onto a second line instead of being cut off with '...';
     the dashboard KPI cards drop to a second row on narrow windows
  2. Separate ADMIN login: the login page now has three tabs - User Login, Register, Admin Login.
     The user tab refuses the administrator account and the admin tab refuses ordinary users.
  3. BUDGET WARNING banner on Dashboard, Receipts and Transactions: red for categories over their budget this
     month, amber for categories at 75 % or more.
Run once from the project folder:   python patch_v12.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


# ============================================================ app.py: wrapping metric values + banner on the dashboard
def f_app(s):
    if "text-overflow: clip" not in s:
        s = swap(s, '[data-testid="stMetricValue"] { font-size: 1.35rem !important; }\n',
                 '[data-testid="stMetricValue"] { font-size: 1.35rem !important; }\n'
                 '[data-testid="stMetricValue"] p, [data-testid="stMetricLabel"] p,\n'
                 '[data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"] {\n'
                 '    white-space: normal !important; overflow: visible !important; text-overflow: clip !important;\n'
                 '    overflow-wrap: anywhere; line-height: 1.25; }\n'
                 '/* the dashboard KPI cards drop to a second row when the window is narrow */\n'
                 '.st-key-kpis [data-testid="stHorizontalBlock"] { display: grid !important;\n'
                 '    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.75rem 1rem; }\n'
                 '.st-key-kpis [data-testid="stColumn"] { width: auto !important; min-width: 0 !important; flex: unset !important; }\n')
    if "ui.budget_banner" not in s:
        s = swap(s, '    st.subheader(t("Hello, {name}!", name=user["username"]))\n',
                 '    st.subheader(t("Hello, {name}!", name=user["username"]))\n    ui.budget_banner(uid)\n')
    if 'st.container(key="kpis")' not in s:
        a = s.index("    k = st.columns(6)\n")
        end_line = '    k[5].metric(t("Forecast next month"), ui.money(fc_total) if fc_total is not None else "—")\n'
        b = s.index(end_line) + len(end_line)
        block = "".join("    " + ln if ln.strip() else ln for ln in s[a:b].splitlines(True))
        s = s[:a] + '    with st.container(key="kpis"):\n' + block + s[b:]
    return s


edit("app.py", f_app)


# ============================================================ utils/ui.py: budget banner
def f_ui(s):
    if "def budget_banner" in s:
        return s
    return s + '''

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
'''


edit("utils/ui.py", f_ui)


def add_banner(path, anchor):
    def fn(s):
        if "ui.budget_banner" in s:
            return s
        return swap(s, anchor, anchor + "ui.budget_banner(uid)\n")
    edit(path, fn)


add_banner("pages/2_Receipts.py", "st.title(f\"{t('Receipt & Transaction Entry')}\")\n")
add_banner("pages/3_Transactions.py", "st.title(f\"{t('Transaction Management')}\")\n")


# ============================================================ pages/1_Account.py: separate admin login
def f_account(s):
    if "tab_admin" in s:
        return s
    a = s.index('    tab_login, tab_reg = st.tabs([t("Login"), t("Register")])\n')
    b = s.index("    with tab_reg:\n")
    new = '''    tab_login, tab_reg, tab_admin = st.tabs([t("User Login"), t("Register"), t("Admin Login")])
    with tab_login:
        with st.form("login_form"):
            u = st.text_input(t("Username"))
            p = st.text_input(t("Password"), type="password")
            ok = st.form_submit_button(t("Log in"), type="primary")
        if ok:
            res, msg = auth.login(u, p)
            if res and res["role"] == "admin":
                st.error(t("This is an administrator account. Please use the Admin Login tab."))
            elif res:
                st.session_state["user"] = res
                st.session_state["_auto_synced"] = False
                st.session_state["_goto_dashboard"] = True
                st.rerun()
            else:
                st.error(t(msg))
    with tab_admin:
        st.caption(t("Administrator access only."))
        with st.form("admin_login_form"):
            au = st.text_input(t("Username"), key="adm_user")
            ap = st.text_input(t("Password"), type="password", key="adm_pw")
            aok = st.form_submit_button(t("Log in as administrator"), type="primary")
        if aok:
            res, msg = auth.login(au, ap)
            if res and res["role"] == "admin":
                st.session_state["user"] = res
                st.session_state["_auto_synced"] = False
                st.session_state["_goto_dashboard"] = True
                st.rerun()
            elif res:
                st.error(t("This account is not an administrator."))
            else:
                st.error(t(msg))
'''
    return s[:a] + new + s[b:]


edit("pages/1_Account.py", f_account)


# ============================================================ utils/i18n.py
def f_i18n(s):
    if "Admin Login" in s:
        return s
    return s + """

MS.update({
    "User Login": "Log Masuk Pengguna",
    "Admin Login": "Log Masuk Admin",
    "Administrator access only.": "Akses pentadbir sahaja.",
    "Log in as administrator": "Log masuk sebagai pentadbir",
    "This is an administrator account. Please use the Admin Login tab.": "Ini akaun pentadbir. Sila guna tab Log Masuk Admin.",
    "This account is not an administrator.": "Akaun ini bukan pentadbir.",
    "Over budget this month: {items}": "Melebihi belanjawan bulan ini: {items}",
    "Close to the budget limit (75% or more): {items}": "Hampir mencapai had belanjawan (75% atau lebih): {items}",
})
"""


edit("utils/i18n.py", f_i18n)
print("Done. Restart Streamlit.")