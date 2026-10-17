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
    if db.email_exists(email):
        return False, "That email is already registered."
    db.create_user(username, email, hash_password(password), "user")
    return True, "Account created. You can now log in."


def login(username, password):
    """Returns (user_dict | None, message)."""
    user = db.get_user_by_username(username or "")
    if not user or not verify_password(password or "", user["password"]):
        return None, "Invalid username or password."
    if not user["is_active"]:
        return None, "This account has been deactivated."
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
