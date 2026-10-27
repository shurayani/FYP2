"""One-time patch #16: receipt IMAGES are synchronised through Supabase Storage, so a receipt uploaded on one
device (laptop, phone, Streamlit Cloud) shows its image on every device - no more 'Image file not found'.

How it works (same offline-first idea as the records):
  * images are still saved locally first (works offline, as in the report)
  * laptop : during every sync (at login / 'Sync now') local images not yet in Supabase are uploaded
  * cloud  : (IPECS_CLOUD = "1") images are uploaded immediately, because the cloud disk is temporary
  * a device that does not have an image downloads it from Supabase the first time the receipt is shown,
    and keeps a local copy
  * deleting / replacing a receipt image also deletes the old copy in Supabase (at the next sync on the laptop)
  * the private bucket 'receipts' is created automatically (needs the secret / service_role key you already use)

Run once from the project folder:   python patch_v16.py
Then commit + push (for the cloud), and press 'Sync now' on the laptop once to upload your existing images."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


# ============================================================ src/image_store.py (new)
(ROOT / "src" / "image_store.py").write_text(r'''"""Receipt images in Supabase Storage (patch #16).

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
''', encoding="utf-8")
print("wrote src/image_store.py")


# ============================================================ src/receipt_manager.py
def f_rm(s):
    if "image_store" in s:
        return s
    s = swap(s, '''    path.write_bytes(data)
    return str(path.relative_to(BASE_DIR)).replace("\\\\", "/")
''', '''    path.write_bytes(data)
    rel = str(path.relative_to(BASE_DIR)).replace("\\\\", "/")
    _cloud_upload(rel)
    return rel


def _cloud():
    return os.getenv("IPECS_CLOUD", "").strip() == "1"


def _cloud_upload(rel):
    """Cloud: the disk is temporary, so the image goes to Supabase Storage at once.
    Laptop: uploaded at the next sync (offline-first)."""
    if _cloud():
        from src import image_store
        image_store.upload(rel)
''')
    s = swap(s, '''    p = get_full_path(rel_path)
    return p.read_bytes() if p.exists() else None
''', '''    p = get_full_path(rel_path)
    if p.exists():
        return p.read_bytes()
    from src import image_store                    # uploaded on another device -> fetch it from Supabase
    return image_store.download(rel_path)
''')
    s = swap(s, '''        if p.exists():
            os.remove(p)
    except OSError:
        pass
''', '''        if p.exists():
            os.remove(p)
    except OSError:
        pass
    from src import image_store                    # remove the Supabase copy too
    image_store.forget(rel_path, now=_cloud())
''')
    return s


edit("src/receipt_manager.py", f_rm)
print("receipt_manager.py ok")


# ============================================================ src/sync_manager.py: images during every sync
def f_sync(s):
    if "image_store" in s:
        return s
    return swap(s, '''        pull_remote(user_id, result)
''', '''        pull_remote(user_id, result)
        try:                                                   # receipt images (patch #16)
            from src import image_store
            result["images"] = image_store.sync_images()
        except Exception:
            pass
''')


edit("src/sync_manager.py", f_sync)
print("sync_manager.py ok")


# ============================================================ src/cloud_mode.py: catch images missed by a save
def f_cloud(s):
    if "image_store" in s:
        return s
    s = swap(s, "PAGE = 1000                                    # Supabase returns at most 1000 rows per request\n",
             "PAGE = 1000                                    # Supabase returns at most 1000 rows per request\n"
             "_last_image_sync = 0.0\n")
    return swap(s, '''    if not ready() or not user_id or user_id == db.ADMIN_ID:
        return
    try:
        if db.sync_counts(user_id)["pending"] == 0:
''', '''    if not ready() or not user_id or user_id == db.ADMIN_ID:
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
''')


edit("src/cloud_mode.py", f_cloud)
print("cloud_mode.py ok")
print("Done. Commit + push, then on the laptop press 'Sync now' once to upload your existing receipt images.")