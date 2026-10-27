"""One-time patch #3:
  * profile card (avatar + name + role) is ONE clickable block that opens the Account page
  * current-page box has the same size/spacing as the other boxes
  * after login you land on the Dashboard
Run once from the project folder:   python patch_v3.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ============================================================ app.py
p = ROOT / "app.py"
s = p.read_text(encoding="utf-8")
if "profilebox" in s:
    print("app.py already patched")
else:
    # 1) css: same-size active box + clickable profile card
    a = s.index(".nav-active {")
    b = s.index("}\n", a) + 2
    new_css = """.nav-active { box-sizing:border-box; height:45px; display:flex; align-items:center; border:1px solid #2E74B5;
    border-radius:8px; padding:0 0.85rem; margin-bottom:12px; background:#2E74B5; color:#ffffff !important;
    font-weight:600; font-size:0.875rem; }

/* profile card = one clickable block that opens the Account page */
.st-key-profilebox { position: relative; }
.st-key-profilebox [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) { position:absolute; inset:0; z-index:5; }
.st-key-profilebox [data-testid="stPageLink-NavLink"] { opacity:0; height:100%; width:100%; }
.profile-card { transition: all .15s ease; }
.st-key-profilebox:hover .profile-card { border-color:#2E74B5; background:#f3f8fd; }
.profile-card.profile-active { background:#e6f1fc; border:2px solid #2E74B5; }
"""
    s = s[:a] + new_css + s[b:]

    # 2) profile block in the sidebar
    a = s.index('        initial = user["username"][:1].upper()')
    b = s.index("        st.divider()", a)
    new_profile = '''        initial = user["username"][:1].upper()
        on_account = (nav.title == account_page.title)
        with st.container(key="profilebox"):
            st.markdown(
                f"<div class='profile-card{' profile-active' if on_account else ''}'>"
                f"<div class='profile-avatar'>{initial}</div>"
                f"<div><div class='profile-name'>{user['username']}</div>"
                f"<div class='profile-role'>{user['role']}</div></div></div>", unsafe_allow_html=True)
            st.page_link(account_page, label=t("Account"))
'''
    s = s[:a] + new_profile + s[b:]

    # 3) land on the dashboard right after login
    marker = 'nav = st.navigation(pages, position="hidden")'
    a = s.index(marker)
    b = s.index("\n", a)
    s = s[:b] + '\nif user and st.session_state.pop("_goto_dashboard", False):\n    st.switch_page(pages[0])' + s[b:]
    p.write_text(s, encoding="utf-8")
    print("app.py patched")

# ============================================================ pages/1_Account.py
p = ROOT / "pages" / "1_Account.py"
s = p.read_text(encoding="utf-8")
if "_goto_dashboard" in s:
    print("1_Account.py already patched")
else:
    old = '                st.session_state["_auto_synced"] = False\n'
    assert old in s, "login block not found in 1_Account.py"
    s = s.replace(old, old + '                st.session_state["_goto_dashboard"] = True\n')
    p.write_text(s, encoding="utf-8")
    print("1_Account.py patched")
print("Done. Restart Streamlit.")