"""Cloud hosting mode (patch #14) - used ONLY when the setting IPECS_CLOUD = "1" is present
(Streamlit Community Cloud secrets). The cloud server's disk is temporary, so Supabase is used as the
permanent copy:
  * push_now(user_id) : send pending changes to Supabase right after they happen
  * restore_all()     : after a restart, pull every account and record back from Supabase into SQLite
On the laptop (no IPECS_CLOUD) nothing here runs and IPECS stays offline-first as described in the report."""
import os
import threading
import time

from src import db_manager as db
from src import sync_manager

PAGE = 1000                                    # Supabase returns at most 1000 rows per request
_restore_lock = threading.Lock()
_nothing_remote_until = 0.0                    # Supabase had no accounts: do not ask again for a while
_last_image_sync = 0.0


def enabled() -> bool:
    return os.getenv("IPECS_CLOUD", "").strip() == "1"


def ready() -> bool:
    return enabled() and sync_manager.is_configured()


def push_now(user_id) -> None:
    """Push this user's pending changes. Never raises: on failure they stay pending and are retried next time."""
    if not ready() or not user_id or user_id == db.ADMIN_ID:
        return
    global _last_image_sync
    import time
    if time.time() - _last_image_sync > 60:                   # images: at most once a minute
        _last_image_sync = time.time()
        try:
            from src import image_store
            image_store.sync_images()
        except Exception:
            pass
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
    global last_restore
    out = {"restored": 0, "failed": 0, "error": None, "errors": [], "at": time.strftime("%Y-%m-%d %H:%M:%S")}
    if not ready():
        out["error"] = "cloud mode is off or Supabase is not configured"
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
                except Exception as e:
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
