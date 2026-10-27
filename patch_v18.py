"""One-time patch #18: 'Cloud / Sync check' tab in the Admin Panel (diagnosis + manual repair).
  * shows what THIS server sees: cloud mode on/off, Supabase configured, where the database is,
    the accounts in the local database and the accounts in Supabase, and the last automatic restore
  * button 'Restore from Supabase now': copies every account and record from Supabase into this server's
    database and lists any record that could not be copied, with the reason
  * every restore is also written to the app log (Manage app on Streamlit Cloud)
Run once from the project folder:   python patch_v18.py      then commit + push + Reboot app."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


# ============================================================ src/cloud_mode.py: record reasons + last result
def f_cloud(s):
    if "last_restore" in s:
        return s
    s = swap(s, '''    out = {"restored": 0, "failed": 0, "error": None}
    if not ready():
        return out
    try:
        for table in db.SYNC_TABLES:''', '''    global last_restore
    out = {"restored": 0, "failed": 0, "error": None, "errors": [], "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    if not ready():
        out["error"] = "cloud mode is off or Supabase is not configured"
        return out
    try:
        for table in db.SYNC_TABLES:''')
    s = swap(s, '''                except Exception:
                    out["failed"] += 1                         # e.g. a record whose parent is missing remotely
    except Exception as e:                                      # Supabase unreachable / wrong key / table missing
        out["error"] = str(e)[:200]
    return out
''', '''                except Exception as e:
                    out["failed"] += 1                         # e.g. a record whose parent is missing remotely
                    if len(out["errors"]) < 10:
                        out["errors"].append(f"{table} {str(r.get('id'))[:8]}: {str(e)[:150]}")
    except Exception as e:                                      # Supabase unreachable / wrong key / table missing
        out["error"] = str(e)[:300]
    last_restore = out
    print(f"[IPECS] restore from Supabase: {out}", flush=True)
    return out


last_restore = None


def check() -> dict:
    """What this server sees - for the Admin Panel 'Cloud / Sync check' tab."""
    from utils.config import DB_PATH
    info = {"cloud_mode": enabled(), "supabase_configured": sync_manager.is_configured(), "db_path": str(DB_PATH),
            "local_users": [], "remote_users": [], "remote_error": None, "last_restore": last_restore}
    with db.get_conn() as c:
        info["local_users"] = [r[0] for r in c.execute(
            "SELECT username FROM users WHERE id<>? ORDER BY username", (db.ADMIN_ID,)).fetchall()]
    if info["supabase_configured"]:
        try:
            info["remote_users"] = sorted(r.get("username") for r in _all_rows("users"))
        except Exception as e:
            info["remote_error"] = str(e)[:300]
    return info
''')
    return s


edit("src/cloud_mode.py", f_cloud)
print("cloud_mode.py ok")


# ============================================================ pages/9_Admin_Panel.py: new tab
def f_admin(s):
    if "tab_cloud" in s:
        return s
    s = swap(s, '''tab_users, tab_sys, tab_cat, tab_tx = st.tabs([t("User Management"), t("System Overview"),
                                               t("Category Management"), t("Transaction Oversight")])''',
             '''tab_users, tab_sys, tab_cat, tab_tx, tab_cloud = st.tabs([t("User Management"), t("System Overview"),
                                               t("Category Management"), t("Transaction Oversight"),
                                               "Cloud / Sync check"])''')
    return s.rstrip("\n") + '''


# ------------------------------------------------------------------ cloud / sync check (patch #18)
with tab_cloud:
    from src import cloud_mode
    info = cloud_mode.check()
    c1, c2 = st.columns(2)
    c1.metric("Cloud mode (IPECS_CLOUD)", "ON" if info["cloud_mode"] else "OFF")
    c2.metric("Supabase configured", "Yes" if info["supabase_configured"] else "No")
    st.caption(f"Database on this server: {info['db_path']}")
    c3, c4 = st.columns(2)
    with c3:
        st.markdown(f"**Accounts in this server's database ({len(info['local_users'])})**")
        st.write(", ".join(info["local_users"]) or "none")
    with c4:
        st.markdown(f"**Accounts in Supabase ({len(info['remote_users'])})**")
        if info["remote_error"]:
            st.error("Supabase could not be read: " + info["remote_error"])
        else:
            st.write(", ".join(info["remote_users"]) or "none")
    missing = sorted(set(info["remote_users"]) - set(info["local_users"]))
    if missing:
        st.warning("In Supabase but NOT on this server (cannot log in here yet): " + ", ".join(missing))
    st.markdown("**Last restore from Supabase**")
    st.json(info["last_restore"] or {"note": "no restore has run since this server started"})
    if st.button("Restore from Supabase now", type="primary"):
        with st.spinner("Copying accounts and records from Supabase..."):
            res = cloud_mode.restore_all()
        if res["error"]:
            st.error("Restore failed: " + res["error"])
        else:
            st.success(f"Restored {res['restored']} record(s); {res['failed']} could not be copied.")
        if res["errors"]:
            st.code("\\n".join(res["errors"]))
'''


edit("pages/9_Admin_Panel.py", f_admin)
print("9_Admin_Panel.py ok")
print("Done. Commit + push + Reboot app, then log in as admin and open Admin Panel > Cloud / Sync check.")