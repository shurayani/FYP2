"""Receipt file storage (Module 2, Section 5.6.2). File-system only; database records for
receipts are handled by db_manager."""
import os
import re
from datetime import datetime
from pathlib import Path

from utils.config import BASE_DIR, MAX_UPLOAD_MB, RECEIPT_DIR

ALLOWED_EXT = {".jpg", ".jpeg", ".png"}


def validate_upload(filename: str, size_bytes: int):
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXT:
        return False, "Only JPEG or PNG images are accepted."
    if size_bytes > MAX_UPLOAD_MB * 1024 * 1024:
        return False, f"Image is larger than {MAX_UPLOAD_MB} MB."
    return True, "OK"


def save_image(user_id: str, filename: str, data: bytes) -> str:
    """Save with a user-scoped, timestamp-based name to avoid collisions. Returns path relative to project."""
    ext = Path(filename).suffix.lower() or ".jpg"
    safe = re.sub(r"[^A-Za-z0-9_-]", "", Path(filename).stem)[:30] or "receipt"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    name = f"{user_id[:8]}_{stamp}_{safe}{ext}"
    path = RECEIPT_DIR / name
    path.write_bytes(data)
    rel = str(path.relative_to(BASE_DIR)).replace("\\", "/")
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


def get_full_path(rel_path: str) -> Path:
    return BASE_DIR / rel_path


def read_image_bytes(rel_path: str):
    p = get_full_path(rel_path)
    if p.exists():
        return p.read_bytes()
    from src import image_store                    # uploaded on another device -> fetch it from Supabase
    return image_store.download(rel_path)


def replace_image(user_id: str, old_rel_path: str, filename: str, data: bytes) -> str:
    new_rel = save_image(user_id, filename, data)
    delete_image(old_rel_path)
    return new_rel


def delete_image(rel_path: str):
    try:
        p = get_full_path(rel_path)
        if p.exists():
            os.remove(p)
    except OSError:
        pass
    from src import image_store                    # remove the Supabase copy too
    image_store.forget(rel_path, now=_cloud())
