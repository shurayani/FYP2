"""One-time patch: profile card + light-blue sidebar menu in app.py, and the sync ordering fix.
Run once from the project folder:   python patch_ui.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ---------------------------------------------------------------- app.py
p = ROOT / "app.py"
s = p.read_text(encoding="utf-8")
if "profile-card" in s:
    print("app.py already patched")
else:
    a = s.index("/* sidebar navigation")
    b = s.index("/* metric cards */")
    new_css = """/* sidebar: profile card + light-blue page boxes */
[data-testid="stSidebar"] { border-right: 1px solid #cfe2f5; background: #f4f9fe; }
.profile-card { display:flex; align-items:center; gap:12px; padding:0.8rem 0.9rem; margin-bottom:0.9rem;
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

"""
    s = s[:a] + new_css + s[b:]
    s = s.replace('    nav = st.navigation([st.Page("pages/1_Account.py", title=t("Login / Register"))])',
                  '    pages = [st.Page("pages/1_Account.py", title=t("Login / Register"))]\n'
                  '    nav = st.navigation(pages, position="hidden")')
    s = s.replace("    nav = st.navigation(pages)\n", '    nav = st.navigation(pages, position="hidden")   # our own sidebar menu is drawn below\n')
    a = s.index("# ----------------------------------------------------------------------------- sidebar")
    b = s.index("nav.run()")
    sidebar = '''# ----------------------------------------------------------------------------- sidebar
with st.sidebar:
    if user:
        initial = user["username"][:1].upper()
        st.markdown(
            f"<div class='profile-card'><div class='profile-avatar'>{initial}</div>"
            f"<div><div class='profile-name'>{user['username']}</div>"
            f"<div class='profile-role'>{user['role']}</div></div></div>", unsafe_allow_html=True)
        for p_ in pages:
            st.page_link(p_, label=p_.title)
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

# ---------------------------------------------------------------- src/sync_manager.py
p = ROOT / "src" / "sync_manager.py"
s = p.read_text(encoding="utf-8")
if "pending.sort" in s:
    print("sync_manager.py already patched")
else:
    old = '    for entry in db.get_sync_entries(user_id, "pending"):'
    new = ('    pending = db.get_sync_entries(user_id, "pending")\n'
           '    # parents before children, otherwise Supabase rejects rows whose foreign keys are missing\n'
           '    pending.sort(key=lambda e: (db.SYNC_TABLES.index(e["table_name"]), e["local_updated_at"]))\n'
           '    for entry in pending:')
    assert old in s, "push_pending loop not found"
    p.write_text(s.replace(old, new), encoding="utf-8")
    print("sync_manager.py patched")
print("Done. Restart Streamlit.")