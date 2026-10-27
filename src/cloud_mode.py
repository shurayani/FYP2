"""Cloud hosting mode (patch #14) - used ONLY when the setting IPECS_CLOUD = "1" is present
(Streamlit Community Cloud secrets). The cloud server's disk is temporary, so Supabase is used as the
permanent copy:
  * push_now(user_id) : send pending changes to Supabase right after they happen
  * restore_all()     : after a restart, pull every account and record back from Supabase into SQLite
On the laptop (no IPECS_CLOUD) nothing here runs and IPECS stays offline-first as described in the report."""
import os

from src import db_manager as db
from src import sync_manager

PAGE = 1000                                    # Supabase returns at most 1000 rows per request
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
