"""TEMPORARY diagnostics (patch_debug.py)."""
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
