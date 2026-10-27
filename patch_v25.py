"""One-time patch #25: pages remember the section you are on when you switch language or dark mode.

Why it happened: st.tabs does not remember the selected tab. Switching the language renames the tabs
(History -> Sejarah) and dark mode adds a style element above the page, so Streamlit treated the tabs as new
ones and opened the first tab again.
Fix: the tab rows on Transactions, Receipts, Budget Goals, Account and the Admin Panel become a
section switcher whose choice is kept in the session (it works on Streamlit 1.50 and newer).
Run once from the project folder:   python patch_v25.py      then commit + push + Reboot app."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


# ============================================================ utils/ui.py: the switcher
def f_ui(s):
    if "def view_switcher" in s:
        return s
    return s + r'''


def view_switcher(key, options: dict, default):
    """Row of section buttons that replaces st.tabs and REMEMBERS the chosen section when the language or
    dark mode changes. options = {section id: label}; returns the chosen section id."""
    store = f"_view_{key}"
    current = st.session_state.get(store, default)
    if current not in options:
        current = default
    widget_key = f"{key}_{st.session_state.get('lang', 'en')}"      # new labels = new widget, same choice

    def _changed():
        chosen = st.session_state.get(widget_key)
        if chosen is None:                                         # clicking the active section again
            st.session_state[widget_key] = st.session_state.get(store, default)
        else:
            st.session_state[store] = chosen

    extra = {} if widget_key in st.session_state else {"default": current}   # avoids Streamlit's double-value warning
    st.segmented_control("section", list(options.keys()), format_func=lambda k: options[k],
                         key=widget_key, on_change=_changed, label_visibility="collapsed", **extra)
    st.session_state[store] = current
    return current
'''


edit("utils/ui.py", f_ui)


def convert(path, old_tabs_line, new_switcher, withs):
    """Replace the st.tabs line by the switcher and every 'with tab_x:' by 'if _view == "id":'."""
    def fn(s):
        if "ui.view_switcher(" in s:
            return s
        s = swap(s, old_tabs_line, new_switcher)
        for old, new in withs:
            s = swap(s, old, new)
        return s
    edit(path, fn)
    print(path, "ok")


convert("views/3_Transactions.py",
        'tab_hist, tab_bills, tab_price = st.tabs([t("History"), t("Recurring bills"), t("Price check")])\n',
        '_view = ui.view_switcher("tx_view", {"history": t("History"), "bills": t("Recurring bills"),\n'
        '                                      "price": t("Price check")}, "history")\n',
        [("with tab_hist:\n", 'if _view == "history":\n'), ("with tab_bills:\n", 'if _view == "bills":\n'),
         ("with tab_price:\n", 'if _view == "price":\n')])

convert("views/2_Receipts.py",
        'tab_ocr, tab_manual, tab_gallery = st.tabs([t("OCR Receipt Upload"), t("Manual Data Form"), t("Receipt Gallery")])\n',
        '_view = ui.view_switcher("rc_view", {"ocr": t("OCR Receipt Upload"), "manual": t("Manual Data Form"),\n'
        '                                      "gallery": t("Receipt Gallery")}, "ocr")\n',
        [("with tab_ocr:\n", 'if _view == "ocr":\n'), ("with tab_manual:\n", 'if _view == "manual":\n'),
         ("with tab_gallery:\n", 'if _view == "gallery":\n')])

convert("views/5_Budget_Goals.py",
        'tab_cur, tab_hist = st.tabs([t("Current Month"), t("History")])\n',
        '_view = ui.view_switcher("bg_view", {"current": t("Current Month"), "history": t("History")}, "current")\n',
        [("with tab_cur:\n", 'if _view == "current":\n'), ("with tab_hist:\n", 'if _view == "history":\n')])

convert("views/1_Account.py",
        'tab_profile, tab_pw, tab_settings = st.tabs([t("Profile"), t("Change password"), t("Settings")])\n',
        '_view = ui.view_switcher("acc_view", {"profile": t("Profile"), "password": t("Change password"),\n'
        '                                       "settings": t("Settings")}, "profile")\n',
        [("\nwith tab_profile:\n", '\nif _view == "profile":\n'), ("\nwith tab_pw:\n", '\nif _view == "password":\n'),
         ("\nwith tab_settings:\n", '\nif _view == "settings":\n')])

convert("views/9_Admin_Panel.py",
        '''_tab_names = [t("User Management"), t("System Overview"), t("Category Management"), t("Transaction Oversight")]
if _cloud_mode.enabled():                          # diagnosis tab: cloud version only
    _tab_names.append("Cloud / Sync check")
_tabs = st.tabs(_tab_names)
tab_users, tab_sys, tab_cat, tab_tx = _tabs[:4]
tab_cloud = _tabs[4] if len(_tabs) > 4 else None
''',
        '''_views = {"users": t("User Management"), "sys": t("System Overview"), "cat": t("Category Management"),
          "tx": t("Transaction Oversight")}
if _cloud_mode.enabled():                          # diagnosis section: cloud version only
    _views["cloud"] = "Cloud / Sync check"
_view = ui.view_switcher("admin_view", _views, "users")
''',
        [("with tab_users:\n", 'if _view == "users":\n'), ("with tab_sys:\n", 'if _view == "sys":\n'),
         ("with tab_cat:\n", 'if _view == "cat":\n'), ("with tab_tx:\n", 'if _view == "tx":\n'),
         ("if tab_cloud is not None:\n    with tab_cloud:\n", 'if _view == "cloud":\n    if _cloud_mode.enabled():\n')])

print("Done. Commit + push, then Reboot app (and restart Streamlit on the laptop).")