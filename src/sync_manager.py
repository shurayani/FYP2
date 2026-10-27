"""Sync Management (Module 9, FR16-FR19, NFR10-NFR12, Section 5.6.9).

The sync manager never creates or modifies business data itself - it only moves and reconciles
records owned by Modules 1-8. One cycle:

 1. check connectivity + that Supabase is configured/reachable;
 2. detect pending changes (SYNC_LOG rows with sync_status = 'pending');
 3. push them to Supabase (supabase-py) - if the remote copy was changed by another device since the
    last sync, it is a CONFLICT;
 4. conflicts are resolved with last-write-wins on updated_at, the outcome is logged in SYNC_LOG
    (sync_status = 'conflict', resolved_value = winning version) and shown to the user;
 5. pull remote updates (records that are new or newer than the local copy), write them back to the
    local tables and update SYNC_LOG.

Soft-deleted records are synchronised like any other record, so offline deletions reach the server.
"""
import json
from datetime import datetime, timezone

from src import db_manager as db
from src.ocr_module import is_online
from utils.config import SUPABASE_KEY, SUPABASE_URL

_client = None


def is_configured() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def get_client():
    global _client
    if _client is None:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def check_connection():
    """Returns (ok, message)."""
    if not is_configured():
        return False, "Supabase is not configured (set SUPABASE_URL and SUPABASE_KEY in .env)."
    if not is_online():
        return False, "Offline - changes are saved locally and will sync when you are back online."
    try:
        get_client().table("categories").select("id").limit(1).execute()
        return True, "Connected"
    except Exception as e:                                     # unreachable / bad key / schema missing
        return False, f"Supabase not reachable: {str(e)[:120]}"


def resolve(local: dict, remote: dict):
    """Last-write-wins on updated_at. Returns (winner_row, 'local' | 'remote')."""
    if (remote.get("updated_at") or "") > (local.get("updated_at") or ""):
        return remote, "remote"
    return local, "local"


def _remote_row(table, record_id):
    res = get_client().table(table).select("*").eq("id", record_id).limit(1).execute()
    return res.data[0] if res.data else None


_system_categories_ok = False


def ensure_remote_system_categories():
    """System categories must exist in Supabase for the foreign keys (e.g. 'Shopping', added in patch #21)."""
    global _system_categories_ok
    if _system_categories_ok:
        return
    have = {r["id"] for r in (get_client().table("categories").select("id").eq("is_system", 1).execute().data or [])}
    ts = db.now()
    for name in db.SYSTEM_CATEGORIES:
        cid = db.category_uuid(name)
        if cid not in have:
            get_client().table("categories").upsert(dict(id=cid, category_name=name, is_system=1, user_id=None,
                                                         updated_at=ts, is_deleted=0)).execute()
    _system_categories_ok = True


def push_pending(user_id, result):
    ensure_remote_system_categories()
    pending = db.get_sync_entries(user_id, "pending")
    # parents before children, otherwise Supabase rejects rows whose foreign keys are missing
    pending.sort(key=lambda e: (db.SYNC_TABLES.index(e["table_name"]), e["local_updated_at"]))
    for entry in pending:
        table, rid = entry["table_name"], entry["record_id"]
        local = db.get_row(table, rid)
        if local is None:                                        # nothing to send
            db.mark_sync_entry(user_id, table, rid, "synced")
            continue
        remote = _remote_row(table, rid)
        last_seen = entry["remote_updated_at"]                   # remote version we saw at the last sync
        remote_changed = remote is not None and (last_seen is None or remote["updated_at"] > last_seen) \
            and remote["updated_at"] != local["updated_at"]
        if remote_changed:                                       # edited on another device too -> conflict
            winner, side = resolve(local, remote)
            if side == "remote":
                db.apply_remote_row(table, remote)
            else:
                get_client().table(table).upsert(local).execute()
            db.mark_sync_entry(user_id, table, rid, "conflict", remote_updated_at=winner["updated_at"],
                               resolved_value={"kept": side, "version": winner})
            result["conflicts"].append({"table": table, "record_id": rid, "kept": side,
                                        "local_updated_at": local["updated_at"],
                                        "remote_updated_at": remote["updated_at"]})
        else:
            get_client().table(table).upsert(local).execute()
            db.mark_sync_entry(user_id, table, rid, "synced", remote_updated_at=local["updated_at"])
        result["pushed"] += 1


def pull_remote(user_id, result):
    entries_by_key = {(e["table_name"], e["record_id"]): e for e in db.get_sync_entries(user_id)}
    for table in db.SYNC_TABLES:
        q = get_client().table(table).select("*")
        q = q.eq("id", user_id) if table == "users" else q.eq("user_id", user_id)
        remote_rows = q.execute().data or []
        if table == "categories":                                # system categories are identical everywhere
            remote_rows = [r for r in remote_rows if not r.get("is_system")]
        for r in remote_rows:
            local = db.get_row(table, r["id"])
            entry = None
            if local is not None:
                entry = entries_by_key.get((table, r["id"]))
                if entry and entry["sync_status"] == "pending":
                    continue                                     # local change not pushed yet
                if (r["updated_at"] or "") <= (local["updated_at"] or ""):
                    continue
            db.apply_remote_row(table, r)
            db.mark_sync_entry(user_id, table, r["id"], "synced", remote_updated_at=r["updated_at"],
                               local_updated_at=r["updated_at"], operation="update")
            result["pulled"] += 1


def sync_now(user_id) -> dict:
    """Run one full synchronisation cycle. Never raises - errors are reported in the result."""
    result = {"ok": False, "message": "", "pushed": 0, "pulled": 0, "conflicts": [], "at": None}
    if user_id == db.ADMIN_ID:
        result["message"] = "The administrator account is not synchronised."
        return result
    ok, msg = check_connection()
    if not ok:
        result["message"] = msg
        return result
    try:
        push_pending(user_id, result)
        pull_remote(user_id, result)
        try:                                                   # receipt images (patch #16)
            from src import image_store
            result["images"] = image_store.sync_images()
        except Exception:
            pass
        result["ok"] = True
        result["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        result["message"] = (f"Sync complete: {result['pushed']} pushed, {result['pulled']} pulled, "
                             f"{len(result['conflicts'])} conflict(s).")
    except Exception as e:                                      # interrupted connection etc.: nothing is lost,
        result["message"] = f"Sync interrupted: {str(e)[:150]}"  # unsynced records stay 'pending'
    return result


def status(user_id) -> dict:
    """Online/offline state, last sync time, pending count, conflicts (FR19, NFR12)."""
    counts = db.sync_counts(user_id)
    conflicts = []
    for e in db.get_sync_entries(user_id, "conflict"):
        kept = None
        if e["resolved_value"]:
            try:
                kept = json.loads(e["resolved_value"]).get("kept")
            except ValueError:
                pass
        conflicts.append({**e, "kept": kept})
    return {"online": is_online(), "configured": is_configured(), "pending": counts["pending"],
            "synced": counts["synced"], "conflict_count": counts["conflict"],
            "last_sync": counts["last_sync"], "conflicts": conflicts}
