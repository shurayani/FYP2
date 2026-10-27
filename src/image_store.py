"""Receipt images in Supabase Storage (patch #16).

Records (receipts table) were already synchronised; this module synchronises the image FILES.
* upload(rel_path)    : copy one local image to the private bucket
* download(rel_path)  : fetch an image this device does not have (kept locally afterwards)
* forget(rel_path)    : the image was deleted/replaced -> delete it remotely too (queued until the next sync)
* sync_images()       : upload every local image not yet uploaded + apply queued deletions (called by sync)
Every function fails quietly: without Supabase or internet IPECS keeps working offline with local images."""
import mimetypes
import os
import threading
import time
from pathlib import Path

from utils.config import BASE_DIR, DATA_DIR, RECEIPT_DIR

BUCKET = os.getenv("SUPABASE_BUCKET", "receipts").strip() or "receipts"
IMAGE_EXT = {".jpg", ".jpeg", ".png"}
RETRY_AFTER = 300                      # seconds before a failed download is tried again (keeps offline pages fast)

_UPLOADED = DATA_DIR / "uploaded_images.txt"      # names already in Supabase Storage (per device)
_DELETES = DATA_DIR / "image_deletes.txt"         # names to delete remotely at the next sync
_lock = threading.Lock()
_bucket_checked = False
_failed_downloads = {}


def _sync_manager():
    from src import sync_manager
    return sync_manager


def configured() -> bool:
    return _sync_manager().is_configured()


def _name(rel_path) -> str:
    return Path(str(rel_path).replace("\\", "/")).name


def _read(path) -> set:
    try:
        return {x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()}
    except OSError:
        return set()


def _add(path, name):
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(name + "\n")


def _write(path, names):
    with _lock:
        path.write_text("".join(n + "\n" for n in sorted(names)), encoding="utf-8")


def _bucket():
    """The storage bucket; created (private) the first time if it does not exist yet."""
    global _bucket_checked
    storage = _sync_manager().get_client().storage
    if not _bucket_checked:
        try:
            storage.get_bucket(BUCKET)
        except Exception:
            try:
                storage.create_bucket(BUCKET, options={"public": False})
            except Exception:
                pass                       # already exists / no permission: the real error shows on upload
        _bucket_checked = True
    return storage.from_(BUCKET)


def upload(rel_path) -> bool:
    if not configured():
        return False
    p = BASE_DIR / rel_path
    if not p.is_file():
        return False
    name = _name(rel_path)
    ctype = mimetypes.guess_type(name)[0] or "image/jpeg"
    try:
        _bucket().upload(name, p.read_bytes(), {"content-type": ctype, "upsert": "true"})
    except Exception:
        return False
    _add(_UPLOADED, name)
    return True


def download(rel_path):
    """Image bytes from Supabase (saved locally for next time), or None."""
    name = _name(rel_path)
    if not name or not configured() or time.time() - _failed_downloads.get(name, 0) < RETRY_AFTER:
        return None
    try:
        data = _bucket().download(name)
    except Exception:
        data = None
    if not data:
        _failed_downloads[name] = time.time()
        return None
    try:
        p = BASE_DIR / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        _add(_UPLOADED, name)              # it is in Supabase already - never upload it again
    except OSError:
        pass
    return data


def forget(rel_path, now=False):
    """Queue the remote copy for deletion; now=True (cloud) deletes it straight away."""
    name = _name(rel_path)
    if not name:
        return
    _add(_DELETES, name)
    if now:
        _apply_deletes()


def _apply_deletes() -> int:
    names = _read(_DELETES)
    if not names or not configured():
        return 0
    try:
        _bucket().remove(sorted(names))
    except Exception:
        return 0
    _write(_DELETES, _read(_DELETES) - names)
    _write(_UPLOADED, _read(_UPLOADED) - names)
    return len(names)


def sync_images() -> dict:
    """Upload local images that are not in Supabase yet and apply queued deletions."""
    out = {"uploaded": 0, "deleted": 0, "failed": 0}
    if not configured():
        return out
    done, queued = _read(_UPLOADED), _read(_DELETES)
    for p in sorted(RECEIPT_DIR.glob("*")):
        if p.suffix.lower() not in IMAGE_EXT or p.name in done or p.name in queued:
            continue
        if upload(str(p.relative_to(BASE_DIR))):
            out["uploaded"] += 1
        else:
            out["failed"] += 1
    out["deleted"] = _apply_deletes()
    return out
