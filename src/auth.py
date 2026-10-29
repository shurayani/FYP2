"""User authentication and session helpers (Module 1, Section 5.6.1).
Passwords are stored as salted bcrypt hashes (NFR09)."""
import re

import bcrypt

from src import db_manager as db

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def init():
    """Create DB, seed categories and the hard-coded admin account."""
    db.init_db(hash_password)


def register(username, email, password, confirm):
    """Returns (ok, message_key). Everyone who registers gets the 'user' role."""
    username, email = (username or "").strip(), (email or "").strip()
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if not EMAIL_RE.match(email):
        return False, "Please enter a valid email address."
    if len(password or "") < 6:
        return False, "Password must be at least 6 characters."
    if password != confirm:
        return False, "Passwords do not match."
    if db.username_exists(username):
        return False, "That username is already taken."
    remote_user_taken, remote_email_taken = _remote_taken(username, email)      # used on another device (patch #28)
    if remote_user_taken:
        return False, "That username is already taken."
    if remote_email_taken:
        return False, "That email is already registered."
    if db.email_exists(email):
        return False, "That email is already registered."
    db.create_user(username, email, hash_password(password), "user")
    return True, "Account created. You can now log in."


def login(username, password):
    """Returns (user_dict | None, message)."""
    user = db.get_user_by_username(username or "")
    if not user or not verify_password(password or "", user["password"]):
        user = _fetch_account(username or "", password, user)       # registered / changed on another device
        if user is None:
            return None, "Invalid username or password."
    if not user["is_active"]:
        return None, "This account has been deactivated. Contact the administrator to reactivate it."
    return {"id": user["id"], "username": user["username"], "role": user["role"], "email": user["email"]}, "OK"


def update_profile(user_id, username, email):
    username, email = username.strip(), email.strip()
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if not EMAIL_RE.match(email):
        return False, "Please enter a valid email address."
    if db.username_exists(username, exclude_id=user_id):
        return False, "That username is already taken."
    if db.email_exists(email, exclude_id=user_id):
        return False, "That email is already registered."
    db.update_user(user_id, username=username, email=email)
    return True, "Profile updated."


def change_password(user_id, current, new, confirm):
    user = db.get_user(user_id)
    if not user or not verify_password(current, user["password"]):
        return False, "Current password is incorrect."
    if len(new) < 6:
        return False, "Password must be at least 6 characters."
    if new != confirm:
        return False, "Passwords do not match."
    db.update_user(user_id, password=hash_password(new))
    return True, "Password changed."


def deactivate_account(user_id):
    db.update_user(user_id, is_active=0)


def set_active(user_id, active: bool):
    db.update_user(user_id, is_active=int(active))


# ---------------------------------------------------------------- accounts created on another device (patch #28)
def _remote_client():
    """Supabase client when Supabase is configured and this device is online, else None (never raises)."""
    try:
        from src import sync_manager
        from src.ocr_module import is_online
        if not sync_manager.is_configured() or not is_online(1.5):
            return None
        return sync_manager.get_client()
    except Exception:
        return None


def _like(text):
    """Exact (case-insensitive) match for ilike: escape the wildcards % and _ ."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _remote_user(username):
    client = _remote_client()
    if client is None or not username:
        return None
    try:
        rows = client.table("users").select("*").ilike("username", _like(username.strip())).limit(5).execute().data or []
    except Exception:
        return None
    rows = [r for r in rows if str(r.get("username", "")).lower() == username.strip().lower()]
    return rows[0] if rows else None


def _remote_taken(username, email):
    """(username_taken, email_taken) in Supabase; (False, False) when offline or not configured."""
    client = _remote_client()
    if client is None:
        return False, False
    try:
        u = _remote_user(username) is not None
        rows = client.table("users").select("id,email").ilike("email", _like(email.strip())).limit(5).execute().data or []
        e = any(str(r.get("email", "")).lower() == email.strip().lower() for r in rows)
        return u, e
    except Exception:
        return False, False


def _fetch_account(username, password, local):
    """The account exists in Supabase with this password -> copy it to this device. Returns the local row or None."""
    remote = _remote_user(username)
    if not remote or not verify_password(password or "", remote.get("password") or ""):
        return None
    if local is not None and local["id"] != remote["id"]:
        return None                                   # a different person with the same name on this device
    try:
        db.apply_remote_row("users", remote)
        db.mark_sync_entry(remote["id"], "users", remote["id"], "synced", remote_updated_at=remote.get("updated_at"),
                           local_updated_at=remote.get("updated_at"), operation="update")
    except Exception:
        return None
    return db.get_user_by_username(username)
