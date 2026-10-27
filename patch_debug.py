"""TEMPORARY diagnostic patch: writes '[IPECS-DEBUG]' lines to the app log (Manage app on Streamlit Cloud)
showing where the database file is, what kind of disk it is on, and whether its tables are visible
right after start-up and at every login attempt. Changes nothing else.
Run once:   python patch_debug.py      then commit + push + Reboot app, try to log in, and copy the
[IPECS-DEBUG] lines from the log. Remove later with:  git revert <commit>"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

(ROOT / "src" / "debug_info.py").write_text(r'''"""TEMPORARY diagnostics (patch_debug.py)."""
import os
import sqlite3
import threading


def _fs_type(path):
    """File-system type of the disk that holds `path` (from /proc/mounts; Linux only)."""
    best, kind = "", "?"
    try:
        real = os.path.realpath(path)
        with open("/proc/mounts", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) > 2 and (real == parts[1] or real.startswith(parts[1].rstrip("/") + "/")) \
                        and len(parts[1]) >= len(best):
                    best, kind = parts[1], parts[2]
    except OSError:
        pass
    return f"{kind} (mounted at {best or '?'})"


def log(tag):
    try:
        from src import db_manager as db
        p = str(db.DB_PATH)
        info = {"tag": tag, "pid": os.getpid(), "thread": threading.current_thread().name, "db": p,
                "exists": os.path.exists(p), "size": os.path.getsize(p) if os.path.exists(p) else None,
                "disk": _fs_type(os.path.dirname(p)), "home_disk": _fs_type(os.path.expanduser("~")),
                "tmp_disk": _fs_type("/tmp"), "sqlite": sqlite3.sqlite_version,
                "IPECS_CLOUD": os.getenv("IPECS_CLOUD"), "has_ADMIN_PASSWORD": bool(os.getenv("ADMIN_PASSWORD")),
                "has_SUPABASE_KEY": bool(os.getenv("SUPABASE_KEY"))}
        if os.path.exists(p):
            c = sqlite3.connect(p)
            tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            info["tables"] = len(tables)
            if "users" in tables:
                info["users"] = [r[0] for r in c.execute("SELECT username FROM users")]
            c.close()
        print("[IPECS-DEBUG]", info, flush=True)
    except Exception as e:
        print("[IPECS-DEBUG] failed", tag, repr(e), flush=True)
''', encoding="utf-8")
print("wrote src/debug_info.py")

p = ROOT / "app.py"
s = p.read_text(encoding="utf-8")
anchor = "auth.init()                                    # create DB, seed 7 categories + admin on first launch\n"
if "debug_info" not in s:
    assert anchor in s, "anchor not found in app.py"
    s = s.replace(anchor, anchor + "from src import debug_info  # noqa: E402  (TEMPORARY)\ndebug_info.log(\"after auth.init\")\n", 1)
    p.write_text(s, encoding="utf-8")
print("app.py ok")

p = ROOT / "src" / "auth.py"
s = p.read_text(encoding="utf-8")
anchor = '    """Returns (user_dict | None, message)."""\n'
if "debug_info" not in s:
    assert anchor in s, "anchor not found in auth.py"
    s = s.replace(anchor, anchor + '    from src import debug_info  # TEMPORARY\n    debug_info.log("login " + str(username))\n', 1)
    p.write_text(s, encoding="utf-8")
print("auth.py ok")
print("Done. Commit + push + Reboot app, try to log in, then copy the [IPECS-DEBUG] lines from the log.")