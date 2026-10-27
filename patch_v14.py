"""One-time patch #14 (version 2): run IPECS on FREE Streamlit Community Cloud for UAT with REAL users,
without your laptop being on, and without losing their data when the cloud server restarts.

Streamlit Community Cloud deletes local files (the SQLite database) whenever the app sleeps or restarts.
With the setting IPECS_CLOUD = "1" (set on the cloud only, never on your laptop):
  * every change is pushed to Supabase straight away (not only at login), and
  * when the cloud server starts again, all accounts and records are pulled back from Supabase,
    so users can log in and see their transactions as before.
  Receipt IMAGES are files and are not restored after a restart (transactions are).

Also:
  * requirements.txt : opencv-python -> opencv-python-headless (needed on the cloud; your laptop is not affected)
  * ocr_module.py    : online check also tries Gemini's server on port 443 (some cloud servers block the old check)
  * optional IPECS_DEMO = "1" creates demo / demo123 with sample data (leave it out for real-user UAT)

Your laptop version is unchanged: without IPECS_CLOUD it keeps the offline-first behaviour from the report.
Run once from the project folder:   python patch_v14.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


# ============================================================ src/cloud_mode.py (new)
(ROOT / "src" / "cloud_mode.py").write_text(r'''"""Cloud hosting mode (patch #14) - used ONLY when the setting IPECS_CLOUD = "1" is present
(Streamlit Community Cloud secrets). The cloud server's disk is temporary, so Supabase is used as the
permanent copy:
  * push_now(user_id) : send pending changes to Supabase right after they happen
  * restore_all()     : after a restart, pull every account and record back from Supabase into SQLite
On the laptop (no IPECS_CLOUD) nothing here runs and IPECS stays offline-first as described in the report."""
import os

from src import db_manager as db
from src import sync_manager

PAGE = 1000                                    # Supabase returns at most 1000 rows per request


def enabled() -> bool:
    return os.getenv("IPECS_CLOUD", "").strip() == "1"


def ready() -> bool:
    return enabled() and sync_manager.is_configured()


def push_now(user_id) -> None:
    """Push this user's pending changes. Never raises: on failure they stay pending and are retried next time."""
    if not ready() or not user_id or user_id == db.ADMIN_ID:
        return
    try:
        if db.sync_counts(user_id)["pending"] == 0:
            return
        sync_manager.push_pending(user_id, {"pushed": 0, "pulled": 0, "conflicts": []})
    except Exception:
        pass


def _all_rows(table):
    client = sync_manager.get_client()
    out, start = [], 0
    while True:
        res = client.table(table).select("*").range(start, start + PAGE - 1).execute()
        rows = res.data or []
        out.extend(rows)
        if len(rows) < PAGE:
            return out
        start += PAGE


def local_user_count() -> int:
    with db.get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM users WHERE id<>?", (db.ADMIN_ID,)).fetchone()[0]


def restore_all() -> dict:
    """Copy every record from Supabase into the (empty) local database, parents before children.
    Returns {"restored": n, "failed": n, "error": text or None}."""
    out = {"restored": 0, "failed": 0, "error": None}
    if not ready():
        return out
    try:
        for table in db.SYNC_TABLES:
            for r in _all_rows(table):
                if table == "categories" and r.get("is_system"):
                    continue                                   # the 7 system categories already exist locally
                owner = r["id"] if table == "users" else r.get("user_id")
                if not owner or owner == db.ADMIN_ID:
                    continue
                try:
                    db.apply_remote_row(table, r)
                    db.mark_sync_entry(owner, table, r["id"], "synced", remote_updated_at=r["updated_at"],
                                       local_updated_at=r["updated_at"], operation="update")
                    out["restored"] += 1
                except Exception:
                    out["failed"] += 1                         # e.g. a record whose parent is missing remotely
    except Exception as e:                                      # Supabase unreachable / wrong key / table missing
        out["error"] = str(e)[:200]
    return out
''', encoding="utf-8")
print("wrote src/cloud_mode.py")


# ============================================================ app.py
def f_app(s):
    if "cloud_mode" in s:
        return s
    s = swap(s, "from src import analytics, auth, db_manager as db, forecast as fc\n",
             "from src import analytics, auth, cloud_mode, db_manager as db, forecast as fc\n")
    anchor = "auth.init()                                    # create DB, seed 7 categories + admin on first launch\n"
    s = swap(s, anchor, anchor + '''

@st.cache_resource(show_spinner="Loading saved accounts and transactions...")
def _restore_from_supabase_once():
    """Cloud only (IPECS_CLOUD = "1"): the cloud disk was wiped by a restart -> bring everything back from Supabase."""
    if cloud_mode.ready() and cloud_mode.local_user_count() == 0:
        return cloud_mode.restore_all()
    return None


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
_restored = _restore_from_supabase_once()
if _restored and _restored.get("error"):
    _restore_from_supabase_once.clear()        # Supabase was unreachable: try again on the next page load
    st.warning("Saved data could not be loaded from Supabase yet: " + _restored["error"])
if os.getenv("IPECS_DEMO") == "1":
    _seed_demo_once()
''')
    # push pending changes on every page load in cloud mode (sidebar) ...
    s = swap(s, '            ui.run_auto_sync(user["id"])\n',
             '            ui.run_auto_sync(user["id"])\n'
             '            cloud_mode.push_now(user["id"])          # cloud: save changes to Supabase immediately\n')
    # ... and once more after the page ran (changes made without a rerun)
    s = s.rstrip("\n")
    assert s.endswith("nav.run()"), "app.py does not end with nav.run()"
    s += ('\nif user and user["role"] != "admin":\n'
          '    cloud_mode.push_now(user["id"])\n')
    return s


edit("app.py", f_app)
print("app.py ok")


# ============================================================ requirements.txt
def f_req(s):
    if "opencv-python-headless" in s:
        return s
    return swap(s, "opencv-python>=4.8", "opencv-python-headless>=4.8")


edit("requirements.txt", f_req)
print("requirements.txt ok")


# ============================================================ src/ocr_module.py
def f_ocr(s):
    if "generativelanguage.googleapis.com" in s:
        return s
    return swap(s, 'for host, port in (("1.1.1.1", 53), ("8.8.8.8", 53)):',
                'for host, port in (("1.1.1.1", 53), ("8.8.8.8", 53), ("generativelanguage.googleapis.com", 443)):')


edit("src/ocr_module.py", f_ocr)
print("ocr_module.py ok")
print("Done. Commit and push to GitHub, then deploy on https://share.streamlit.io with the secrets Claude gave you.")