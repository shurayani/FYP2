"""One-time patch #28: log in on ANY device with an account created on another device.

Why it happened: the laptop checks the username and password against its OWN database (SQLite). An account
registered on the phone (cloud version) is saved in Supabase, but it only reaches the laptop through a sync - and
a sync only runs after someone logs in. So the laptop had never heard of 'miera' and said "Invalid username or
password". (The same thing could happen on the cloud for an account registered on the laptop after the cloud
server had already started.)

Fix (src/auth.py):
  1. Login: if the username/password does not match locally, IPECS asks Supabase (only when online and Supabase is
     set up). If the account exists there and the password matches, the account is copied to this device and the
     user is logged in; the normal sync right after login then brings in all of that user's records.
     The same check also accepts a password that was changed on another device.
  2. Register: a username or email that is already used on another device (in Supabase) is refused, so two
     different people cannot get the same username.
Offline, everything works exactly as before.
Run once from the project folder:   python patch_v28.py      then restart Streamlit (and commit + push + Reboot app)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


HELPERS = '''

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
    return text.replace("\\\\", "\\\\\\\\").replace("%", "\\\\%").replace("_", "\\\\_")


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
'''


def f_auth(s):
    if "patch #28" in s:
        return s
    s = swap(s, '''    if db.username_exists(username):
        return False, "That username is already taken."
''', '''    if db.username_exists(username):
        return False, "That username is already taken."
    remote_user_taken, remote_email_taken = _remote_taken(username, email)      # used on another device (patch #28)
    if remote_user_taken:
        return False, "That username is already taken."
    if remote_email_taken:
        return False, "That email is already registered."
''')
    s = swap(s, '''    user = db.get_user_by_username(username or "")
    if not user or not verify_password(password or "", user["password"]):
        return None, "Invalid username or password."
''', '''    user = db.get_user_by_username(username or "")
    if not user or not verify_password(password or "", user["password"]):
        user = _fetch_account(username or "", password, user)       # registered / changed on another device
        if user is None:
            return None, "Invalid username or password."
''')
    return s.rstrip("\n") + "\n" + HELPERS


edit("src/auth.py", f_auth)
print("src/auth.py ok")
print("Done. Restart Streamlit on the laptop, then commit + push and Reboot the cloud app.")