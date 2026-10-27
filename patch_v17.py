"""One-time patch #17: fixes 'no such table: users' on Streamlit Cloud - IPECS now heals itself.
  1. cloud (IPECS_CLOUD = "1"): the database is kept OUTSIDE the code folder (in the server's home folder),
     because Streamlit Cloud can clean the code folder when it updates the app from GitHub
  2. every database connection checks that the tables exist and recreates them if they were wiped
     (system categories + admin included), instead of crashing
  3. cloud: whenever the local database is found empty, all accounts and records are pulled back from
     Supabase straight away (not only when the server starts)
Laptop: only point 2 applies (a harmless safety check); everything else stays as before.
Run once from the project folder:   python patch_v17.py      then commit + push."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


# ============================================================ utils/config.py: cloud database outside the code folder
def f_config(s):
    if "IPECS_DATA_DIR" in s:
        return s
    return swap(s, 'DATA_DIR = BASE_DIR / "data"\n',
                'DATA_DIR = BASE_DIR / "data"\n'
                'if os.getenv("IPECS_CLOUD", "").strip() == "1":       # cloud: keep data outside the code folder\n'
                '    DATA_DIR = Path(os.getenv("IPECS_DATA_DIR", "") or (Path.home() / ".ipecs_data"))\n')


edit("utils/config.py", f_config)
print("config.py ok")


# ============================================================ src/db_manager.py: recreate missing tables
def f_db(s):
    if "_ensure_schema" in s:
        return s
    s = swap(s, '''    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
''', '''    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _ensure_schema(conn)
        yield conn
''')
    a = s.index("def init_db(hash_password=None):")
    b = s.index("# --------------------------------------------------------------------------- sync log")
    s = s[:a] + '''_hash_fn = None                                # remembered so a wiped database can be rebuilt with the admin


def _create_schema(c, hash_password=None):
    """Tables + seven system categories + admin account (all idempotent)."""
    c.executescript(SCHEMA)
    n = c.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    if n == 0:
        ts = now()
        for name in SYSTEM_CATEGORIES:
            c.execute("INSERT INTO categories (id, category_name, is_system, user_id, updated_at, is_deleted)"
                      " VALUES (?,?,1,NULL,?,0)", (category_uuid(name), name, ts))
    if hash_password is not None:
        exists = c.execute("SELECT 1 FROM users WHERE id=?", (ADMIN_ID,)).fetchone()
        if not exists:
            ts = now()
            c.execute("INSERT INTO users (id, username, email, password, role, is_active, created_at, updated_at)"
                      " VALUES (?,?,?,?,?,1,?,?)",
                      (ADMIN_ID, ADMIN_USERNAME, ADMIN_EMAIL, hash_password(ADMIN_PASSWORD), "admin", ts, ts))
    c.commit()


def _ensure_schema(c):
    """Safety net: if the database file was emptied or replaced, rebuild it instead of crashing."""
    if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone():
        _create_schema(c, _hash_fn)


def init_db(hash_password=None):
    """Create all tables on first launch, seed the seven system categories and the admin account."""
    global _hash_fn
    if hash_password is not None:
        _hash_fn = hash_password
    with get_conn() as c:
        _create_schema(c, hash_password)


''' + s[b:]
    return s


edit("src/db_manager.py", f_db)
print("db_manager.py ok")


# ============================================================ src/cloud_mode.py: restore whenever the database is empty
def f_cloud(s):
    if "_restore_lock" in s:
        return s
    s = swap(s, "import os\n", "import os\nimport threading\nimport time\n")
    s = swap(s, "PAGE = 1000                                    # Supabase returns at most 1000 rows per request\n",
             "PAGE = 1000                                    # Supabase returns at most 1000 rows per request\n"
             "_restore_lock = threading.Lock()\n"
             "_nothing_remote_until = 0.0                    # Supabase had no accounts: do not ask again for a while\n")
    s += '''

def restore_if_empty():
    """Cloud: if this server's database has no user accounts (restart, or the disk was wiped while running),
    pull everything back from Supabase. Only one restore runs at a time. Returns the result or None."""
    global _nothing_remote_until
    if not ready() or time.time() < _nothing_remote_until or local_user_count() > 0:
        return None
    with _restore_lock:
        if local_user_count() > 0:                    # another visitor restored it meanwhile
            return None
        out = restore_all()
        if not out["error"] and out["restored"] == 0:
            _nothing_remote_until = time.time() + 300
        return out
'''
    return s


edit("src/cloud_mode.py", f_cloud)
print("cloud_mode.py ok")


# ============================================================ app.py: check on every page load (cheap) instead of once
def f_app(s):
    if "restore_if_empty" in s:
        return s
    a = s.index('@st.cache_resource(show_spinner="Loading saved accounts and transactions...")')
    b = s.index('@st.cache_resource(show_spinner="Preparing the demo account')
    s = s[:a] + s[b:]
    return swap(s, '''_restored = _restore_from_supabase_once()
if _restored and _restored.get("error"):
    _restore_from_supabase_once.clear()        # Supabase was unreachable: try again on the next page load
    st.warning("Saved data could not be loaded from Supabase yet: " + _restored["error"])
''', '''if cloud_mode.ready() and cloud_mode.local_user_count() == 0:       # cloud database empty -> pull it back
    with st.spinner("Loading saved accounts and transactions..."):
        _restored = cloud_mode.restore_if_empty()
    if _restored and _restored.get("error"):
        st.warning("Saved data could not be loaded from Supabase yet: " + _restored["error"])
''')


edit("app.py", f_app)
print("app.py ok")
print("Done. Commit + push; on Streamlit Cloud press Reboot app once.")