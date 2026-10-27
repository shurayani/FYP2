"""Database Manager - all SQLite operations for the nine IPECS tables (Section 5.6.6).

* UUID (TEXT) primary keys so records created on different devices never collide.
* Every write sets updated_at; deletions are soft deletes (is_deleted = 1) so they can be synced.
* Every local create / update / delete is recorded as a *pending* entry in SYNC_LOG (Module 9).
* PRAGMA foreign_keys = ON on every connection.
* All getters are scoped by user_id (data isolation, Section 5.8).
"""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from utils.config import (ADMIN_EMAIL, ADMIN_PASSWORD, ADMIN_USERNAME, DB_PATH)

SYSTEM_CATEGORIES = ["Food and Beverage", "Groceries", "Transport", "Utilities",
                     "Education", "Health", "Entertainment", "Shopping"]

ADMIN_ID = "00000000-0000-0000-0000-000000000001"

# Tables that take part in synchronisation, in foreign-key order.
SYNC_TABLES = ["users", "categories", "receipts", "transactions", "transaction_items",
               "budgets", "reports", "anomaly_alerts", "forecasts"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS categories (
    id TEXT PRIMARY KEY,
    category_name TEXT NOT NULL,
    is_system INTEGER NOT NULL DEFAULT 0,
    user_id TEXT REFERENCES users(id),
    updated_at TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS receipts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    file_path TEXT NOT NULL,
    original_filename TEXT,
    upload_date TEXT NOT NULL,
    ocr_raw_text TEXT,
    ocr_engine TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    receipt_id TEXT REFERENCES receipts(id),
    merchant TEXT NOT NULL,
    date TEXT NOT NULL,
    amount REAL NOT NULL,
    category_id TEXT NOT NULL REFERENCES categories(id),
    is_manual INTEGER NOT NULL DEFAULT 1,
    z_score REAL,
    is_anomaly INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS budgets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    category_id TEXT NOT NULL REFERENCES categories(id),
    budget_month TEXT NOT NULL,
    budget_amount REAL NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    report_month TEXT NOT NULL,
    report_data TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS anomaly_alerts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    transaction_id TEXT NOT NULL REFERENCES transactions(id),
    z_score REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    updated_at TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS forecasts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    category_id TEXT NOT NULL REFERENCES categories(id),
    forecast_month TEXT NOT NULL,
    forecast_amount REAL NOT NULL,
    confidence_lower REAL,
    confidence_upper REAL,
    generated_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS transaction_items (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    transaction_id TEXT NOT NULL REFERENCES transactions(id),
    receipt_id TEXT REFERENCES receipts(id),
    item_name TEXT NOT NULL,
    amount REAL NOT NULL,
    category_id TEXT NOT NULL REFERENCES categories(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_items_tx ON transaction_items(transaction_id);
CREATE TABLE IF NOT EXISTS sync_log (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    table_name TEXT NOT NULL,
    record_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    sync_status TEXT NOT NULL DEFAULT 'pending',
    local_updated_at TEXT NOT NULL,
    remote_updated_at TEXT,
    resolved_value TEXT,
    synced_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_sync_record ON sync_log(table_name, record_id);
CREATE INDEX IF NOT EXISTS ix_tx_user_date ON transactions(user_id, date);
CREATE INDEX IF NOT EXISTS ix_sync_user_status ON sync_log(user_id, sync_status);
"""


# --------------------------------------------------------------------------- helpers
def now() -> str:
    """ISO-8601 UTC timestamp with fixed width so string comparison == time comparison."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_id() -> str:
    return str(uuid.uuid4())


def category_uuid(name: str) -> str:
    """Fixed identical IDs for system categories on every device."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, "ipecs.category." + name))


@contextmanager
def get_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        _ensure_schema(conn)
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _rows(cur):
    return [dict(r) for r in cur.fetchall()]


def _row(cur):
    r = cur.fetchone()
    return dict(r) if r else None


# --------------------------------------------------------------------------- init
_hash_fn = None                                # remembered so a wiped database can be rebuilt with the admin


def _create_schema(c, hash_password=None):
    """Tables + seven system categories + admin account (all idempotent)."""
    c.executescript(SCHEMA)
    ts = now()
    for name in SYSTEM_CATEGORIES:                 # also adds system categories introduced later (Shopping)
        if not c.execute("SELECT 1 FROM categories WHERE id=?", (category_uuid(name),)).fetchone():
            c.execute("INSERT INTO categories (id, category_name, is_system, user_id, updated_at, is_deleted)"
                      " VALUES (?,?,1,NULL,?,0)", (category_uuid(name), name, ts))
    if hash_password is not None:
        exists = c.execute("SELECT 1 FROM users WHERE id=?", (ADMIN_ID,)).fetchone()
        if not exists:
            ts = now()
            c.execute("INSERT INTO users (id, username, email, password, role, is_active, created_at, updated_at)"
                      " VALUES (?,?,?,?,?,1,?,?)",
                      (ADMIN_ID, ADMIN_USERNAME, ADMIN_EMAIL, hash_password(ADMIN_PASSWORD), "admin", ts, ts))
    c.commit()


def _ensure_schema(c):
    """Safety net: if the database file was emptied or replaced, rebuild it instead of crashing."""
    if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'").fetchone():
        _create_schema(c, _hash_fn)


def init_db(hash_password=None):
    """Create all tables on first launch, seed the seven system categories and the admin account."""
    global _hash_fn
    if hash_password is not None:
        _hash_fn = hash_password
    with get_conn() as c:
        _create_schema(c, hash_password)


# --------------------------------------------------------------------------- sync log
def _log_change(conn, user_id, table, record_id, operation):
    """Record a local create/update/delete as a pending sync operation (one row per record)."""
    if table not in SYNC_TABLES or user_id is None or user_id == ADMIN_ID:
        return
    ts = now()
    row = conn.execute("SELECT id, operation, sync_status FROM sync_log WHERE table_name=? AND record_id=?",
                       (table, record_id)).fetchone()
    if row is None:
        conn.execute("INSERT INTO sync_log (id, user_id, table_name, record_id, operation, sync_status,"
                     " local_updated_at) VALUES (?,?,?,?,?, 'pending', ?)",
                     (new_id(), user_id, table, record_id, operation, ts))
    else:
        # an un-synced insert stays an insert; a delete always wins
        op = operation
        if row["sync_status"] == "pending" and row["operation"] == "insert" and operation == "update":
            op = "insert"
        conn.execute("UPDATE sync_log SET operation=?, sync_status='pending', local_updated_at=?,"
                     " resolved_value=NULL WHERE id=?", (op, ts, row["id"]))


def _insert(conn, table, data, owner_id):
    cols = ", ".join(data.keys())
    marks = ", ".join("?" for _ in data)
    conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(data.values()))
    _log_change(conn, owner_id, table, data["id"], "insert")


def _update(conn, table, record_id, fields, owner_id, operation="update"):
    fields = dict(fields)
    fields["updated_at"] = now()
    sets = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE {table} SET {sets} WHERE id=?", list(fields.values()) + [record_id])
    _log_change(conn, owner_id, table, record_id, operation)


# --------------------------------------------------------------------------- USERS (Module 1)
def create_user(username, email, password_hash, role="user"):
    uid, ts = new_id(), now()
    with get_conn() as c:
        _insert(c, "users", dict(id=uid, username=username.strip(), email=email.strip().lower(),
                                 password=password_hash, role=role, is_active=1,
                                 created_at=ts, updated_at=ts), uid)
    return uid


def get_user(user_id):
    with get_conn() as c:
        return _row(c.execute("SELECT * FROM users WHERE id=?", (user_id,)))


def get_user_by_username(username):
    with get_conn() as c:
        return _row(c.execute("SELECT * FROM users WHERE lower(username)=lower(?)", (username.strip(),)))


def email_exists(email, exclude_id=None):
    with get_conn() as c:
        r = c.execute("SELECT id FROM users WHERE lower(email)=lower(?)", (email.strip(),)).fetchone()
    return bool(r and r["id"] != exclude_id)


def username_exists(username, exclude_id=None):
    with get_conn() as c:
        r = c.execute("SELECT id FROM users WHERE lower(username)=lower(?)", (username.strip(),)).fetchone()
    return bool(r and r["id"] != exclude_id)


def update_user(user_id, **fields):
    allowed = {k: v for k, v in fields.items() if k in ("username", "email", "password", "is_active", "role")}
    if "email" in allowed:
        allowed["email"] = allowed["email"].strip().lower()
    with get_conn() as c:
        _update(c, "users", user_id, allowed, user_id)


def list_users():
    with get_conn() as c:
        return _rows(c.execute("""
            SELECT u.*, (SELECT COUNT(*) FROM transactions t WHERE t.user_id=u.id AND t.is_deleted=0) AS tx_count
            FROM users u ORDER BY u.created_at"""))


# --------------------------------------------------------------------------- CATEGORIES (Module 4)
def get_categories(user_id, include_system=True):
    """System categories + the user's own custom categories (not deleted)."""
    with get_conn() as c:
        if include_system:
            cur = c.execute("SELECT * FROM categories WHERE is_deleted=0 AND (is_system=1 OR user_id=?)"
                            " ORDER BY is_system DESC, category_name", (user_id,))
        else:
            cur = c.execute("SELECT * FROM categories WHERE is_deleted=0 AND is_system=0 AND user_id=?"
                            " ORDER BY category_name", (user_id,))
        return _rows(cur)


def get_all_categories():
    with get_conn() as c:
        return _rows(c.execute("SELECT * FROM categories WHERE is_deleted=0 ORDER BY is_system DESC, category_name"))


def get_category(category_id):
    with get_conn() as c:
        return _row(c.execute("SELECT * FROM categories WHERE id=?", (category_id,)))


def category_name_taken(name, user_id):
    with get_conn() as c:
        r = c.execute("SELECT 1 FROM categories WHERE is_deleted=0 AND lower(category_name)=lower(?)"
                      " AND (is_system=1 OR user_id=?)", (name.strip(), user_id)).fetchone()
    return bool(r)


def add_category(name, user_id=None, is_system=False):
    cid = new_id()
    with get_conn() as c:
        _insert(c, "categories", dict(id=cid, category_name=name.strip(), is_system=int(is_system),
                                      user_id=None if is_system else user_id, updated_at=now(), is_deleted=0),
                user_id if not is_system else None)
    return cid


def rename_category(category_id, new_name, owner_id):
    with get_conn() as c:
        _update(c, "categories", category_id, {"category_name": new_name.strip()}, owner_id)


def count_category_usage(category_id, user_id=None):
    with get_conn() as c:
        q = "SELECT COUNT(*) FROM transactions WHERE category_id=? AND is_deleted=0"
        args = [category_id]
        if user_id:
            q += " AND user_id=?"
            args.append(user_id)
        return c.execute(q, args).fetchone()[0]


def delete_category(category_id, owner_id, reassign_to=None):
    """Soft-delete a category; optionally reassign its transactions first. Budgets/forecasts of the
    category are soft-deleted as well."""
    with get_conn() as c:
        if reassign_to:
            for t in _rows(c.execute("SELECT id, user_id FROM transactions WHERE category_id=? AND is_deleted=0",
                                     (category_id,))):
                _update(c, "transactions", t["id"], {"category_id": reassign_to}, t["user_id"])
                for it in _rows(c.execute("SELECT id FROM transaction_items WHERE transaction_id=? AND is_deleted=0", (t["id"],))):
                    _update(c, "transaction_items", it["id"], {"category_id": reassign_to}, t["user_id"])
        for table in ("budgets", "forecasts"):
            for r in _rows(c.execute(f"SELECT id, user_id FROM {table} WHERE category_id=? AND is_deleted=0",
                                     (category_id,))):
                _update(c, table, r["id"], {"is_deleted": 1}, r["user_id"], "delete")
        _update(c, "categories", category_id, {"is_deleted": 1}, owner_id, "delete")


def category_summary(user_id):
    """Per-category transaction count and total for the category screen."""
    with get_conn() as c:
        return _rows(c.execute("""
            SELECT c.id, c.category_name, c.is_system, COUNT(t.id) AS tx_count, COALESCE(SUM(t.amount),0) AS total
            FROM categories c LEFT JOIN transactions t
              ON t.category_id=c.id AND t.is_deleted=0 AND t.user_id=?
            WHERE c.is_deleted=0 AND (c.is_system=1 OR c.user_id=?)
            GROUP BY c.id ORDER BY c.is_system DESC, c.category_name""", (user_id, user_id)))


def category_summary_all():
    with get_conn() as c:
        return _rows(c.execute("""
            SELECT c.id, c.category_name, c.is_system, c.user_id, COUNT(t.id) AS tx_count,
                   COALESCE(SUM(t.amount),0) AS total
            FROM categories c LEFT JOIN transactions t ON t.category_id=c.id AND t.is_deleted=0
            WHERE c.is_deleted=0 GROUP BY c.id ORDER BY c.is_system DESC, c.category_name"""))


# --------------------------------------------------------------------------- RECEIPTS (Module 2)
def add_receipt(user_id, file_path, original_filename, ocr_raw_text, ocr_engine):
    rid, ts = new_id(), now()
    with get_conn() as c:
        _insert(c, "receipts", dict(id=rid, user_id=user_id, file_path=file_path,
                                    original_filename=original_filename, upload_date=ts,
                                    ocr_raw_text=ocr_raw_text, ocr_engine=ocr_engine,
                                    created_at=ts, updated_at=ts, is_deleted=0), user_id)
    return rid


def get_receipts(user_id):
    with get_conn() as c:
        return _rows(c.execute("""
            SELECT r.*, COUNT(t.id) AS tx_count, COALESCE(SUM(t.amount), 0) AS tx_amount,
                   MIN(t.merchant) AS tx_merchant
            FROM receipts r LEFT JOIN transactions t ON t.receipt_id=r.id AND t.is_deleted=0
            WHERE r.user_id=? AND r.is_deleted=0 GROUP BY r.id ORDER BY r.upload_date DESC""", (user_id,)))


def get_receipt(receipt_id):
    with get_conn() as c:
        return _row(c.execute("SELECT * FROM receipts WHERE id=?", (receipt_id,)))


def update_receipt(receipt_id, user_id, **fields):
    allowed = {k: v for k, v in fields.items()
               if k in ("file_path", "original_filename", "ocr_raw_text", "ocr_engine")}
    with get_conn() as c:
        _update(c, "receipts", receipt_id, allowed, user_id)


def delete_receipt(receipt_id, user_id):
    """Soft-delete the receipt and unlink it from its transaction (the transaction is kept)."""
    with get_conn() as c:
        for t in _rows(c.execute("SELECT id FROM transactions WHERE receipt_id=? AND is_deleted=0", (receipt_id,))):
            _update(c, "transactions", t["id"], {"receipt_id": None}, user_id)
        _update(c, "receipts", receipt_id, {"is_deleted": 1}, user_id, "delete")


def count_receipts_all():
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM receipts WHERE is_deleted=0").fetchone()[0]


# --------------------------------------------------------------------------- TRANSACTIONS (Module 3)
_TX_SELECT = """SELECT t.*, c.category_name, u.username,
                (SELECT COUNT(*) FROM transaction_items i WHERE i.transaction_id=t.id AND i.is_deleted=0) AS item_count
                FROM transactions t
                JOIN categories c ON c.id=t.category_id JOIN users u ON u.id=t.user_id"""


def add_transaction(user_id, merchant, date, amount, category_id, is_manual=True, receipt_id=None):
    tid, ts = new_id(), now()
    with get_conn() as c:
        _insert(c, "transactions", dict(id=tid, user_id=user_id, receipt_id=receipt_id,
                                        merchant=merchant.strip(), date=str(date), amount=float(amount),
                                        category_id=category_id, is_manual=int(is_manual), z_score=None,
                                        is_anomaly=0, created_at=ts, updated_at=ts, is_deleted=0), user_id)
    return tid


def get_transactions(user_id=None, start=None, end=None, category_id=None, min_amount=None,
                     max_amount=None, is_manual=None):
    q = _TX_SELECT + " WHERE t.is_deleted=0"
    args = []
    if user_id:
        q += " AND t.user_id=?"; args.append(user_id)
    if start:
        q += " AND t.date>=?"; args.append(str(start))
    if end:
        q += " AND t.date<=?"; args.append(str(end))
    if category_id:
        q += " AND t.category_id=?"; args.append(category_id)
    if min_amount is not None:
        q += " AND t.amount>=?"; args.append(float(min_amount))
    if max_amount is not None:
        q += " AND t.amount<=?"; args.append(float(max_amount))
    if is_manual is not None:
        q += " AND t.is_manual=?"; args.append(int(is_manual))
    q += " ORDER BY t.date DESC, t.created_at DESC"
    with get_conn() as c:
        return _rows(c.execute(q, args))


def get_transaction(tx_id):
    with get_conn() as c:
        return _row(c.execute(_TX_SELECT + " WHERE t.id=?", (tx_id,)))


def update_transaction(tx_id, user_id, **fields):
    allowed = {k: v for k, v in fields.items()
               if k in ("merchant", "date", "amount", "category_id", "receipt_id", "z_score", "is_anomaly")}
    if "date" in allowed:
        allowed["date"] = str(allowed["date"])
    with get_conn() as c:
        _update(c, "transactions", tx_id, allowed, user_id)
        if "category_id" in allowed:
            for it in _rows(c.execute("SELECT id FROM transaction_items WHERE transaction_id=? AND is_deleted=0", (tx_id,))):
                _update(c, "transaction_items", it["id"], {"category_id": allowed["category_id"]}, user_id)


def delete_transaction(tx_id, user_id):
    with get_conn() as c:
        for a in _rows(c.execute("SELECT id FROM anomaly_alerts WHERE transaction_id=? AND is_deleted=0", (tx_id,))):
            _update(c, "anomaly_alerts", a["id"], {"is_deleted": 1}, user_id, "delete")
        for it in _rows(c.execute("SELECT id FROM transaction_items WHERE transaction_id=? AND is_deleted=0", (tx_id,))):
            _update(c, "transaction_items", it["id"], {"is_deleted": 1}, user_id, "delete")
        _update(c, "transactions", tx_id, {"is_deleted": 1}, user_id, "delete")


def count_transactions_all():
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM transactions WHERE is_deleted=0").fetchone()[0]


# --------------------------------------------------------------------------- BUDGETS (Module 5)
def get_budgets(user_id, month=None):
    q = ("SELECT b.*, c.category_name FROM budgets b JOIN categories c ON c.id=b.category_id"
         " WHERE b.is_deleted=0 AND b.user_id=?")
    args = [user_id]
    if month:
        q += " AND b.budget_month=?"; args.append(month)
    q += " ORDER BY b.budget_month DESC, c.category_name"
    with get_conn() as c:
        return _rows(c.execute(q, args))


def upsert_budget(user_id, category_id, month, amount):
    with get_conn() as c:
        ex = c.execute("SELECT id FROM budgets WHERE user_id=? AND category_id=? AND budget_month=?"
                       " AND is_deleted=0", (user_id, category_id, month)).fetchone()
        if ex:
            _update(c, "budgets", ex["id"], {"budget_amount": float(amount)}, user_id)
            return ex["id"]
        bid, ts = new_id(), now()
        _insert(c, "budgets", dict(id=bid, user_id=user_id, category_id=category_id, budget_month=month,
                                   budget_amount=float(amount), created_at=ts, updated_at=ts, is_deleted=0), user_id)
        return bid


def update_budget(budget_id, user_id, amount):
    with get_conn() as c:
        _update(c, "budgets", budget_id, {"budget_amount": float(amount)}, user_id)


def delete_budget(budget_id, user_id):
    with get_conn() as c:
        _update(c, "budgets", budget_id, {"is_deleted": 1}, user_id, "delete")


# --------------------------------------------------------------------------- REPORTS (Module 6)
def save_report(user_id, month, data: dict):
    """Insert a report for the month, or overwrite (regenerate) the existing one."""
    payload = json.dumps(data)
    with get_conn() as c:
        ex = c.execute("SELECT id FROM reports WHERE user_id=? AND report_month=? AND is_deleted=0",
                       (user_id, month)).fetchone()
        if ex:
            _update(c, "reports", ex["id"], {"report_data": payload, "generated_at": now()}, user_id)
            return ex["id"]
        rid, ts = new_id(), now()
        _insert(c, "reports", dict(id=rid, user_id=user_id, report_month=month, report_data=payload,
                                   generated_at=ts, updated_at=ts, is_deleted=0), user_id)
        return rid


def get_reports(user_id):
    with get_conn() as c:
        return _rows(c.execute("SELECT * FROM reports WHERE user_id=? AND is_deleted=0 ORDER BY report_month DESC",
                               (user_id,)))


def delete_report(report_id, user_id):
    with get_conn() as c:
        _update(c, "reports", report_id, {"is_deleted": 1}, user_id, "delete")


# --------------------------------------------------------------------------- ANOMALY ALERTS (Module 7)
def get_alerts(user_id, status=None):
    q = ("SELECT a.*, t.merchant, t.date, t.amount, c.category_name FROM anomaly_alerts a"
         " JOIN transactions t ON t.id=a.transaction_id JOIN categories c ON c.id=t.category_id"
         " WHERE a.is_deleted=0 AND t.is_deleted=0 AND a.user_id=?")
    args = [user_id]
    if status == "resolved":
        q += " AND a.status IN ('reviewed','dismissed')"
    elif status:
        q += " AND a.status=?"; args.append(status)
    q += " ORDER BY ABS(a.z_score) DESC"
    with get_conn() as c:
        return _rows(c.execute(q, args))


def get_alert_for_transaction(tx_id):
    with get_conn() as c:
        return _row(c.execute("SELECT * FROM anomaly_alerts WHERE transaction_id=? AND is_deleted=0", (tx_id,)))


def add_alert(user_id, tx_id, z_score):
    aid, ts = new_id(), now()
    with get_conn() as c:
        _insert(c, "anomaly_alerts", dict(id=aid, user_id=user_id, transaction_id=tx_id, z_score=float(z_score),
                                          status="active", created_at=ts, resolved_at=None, updated_at=ts,
                                          is_deleted=0), user_id)
    return aid


def update_alert(alert_id, user_id, **fields):
    allowed = {k: v for k, v in fields.items() if k in ("z_score", "status", "resolved_at", "is_deleted")}
    with get_conn() as c:
        _update(c, "anomaly_alerts", alert_id, allowed, user_id,
                "delete" if allowed.get("is_deleted") else "update")


def set_alert_status(alert_id, user_id, status):
    update_alert(alert_id, user_id, status=status,
                 resolved_at=None if status == "active" else now())


def clear_resolved_alerts(user_id):
    n = 0
    for a in get_alerts(user_id, "resolved"):
        update_alert(a["id"], user_id, is_deleted=1)
        n += 1
    return n


def count_active_alerts_all():
    with get_conn() as c:
        return c.execute("SELECT COUNT(*) FROM anomaly_alerts WHERE is_deleted=0 AND status='active'").fetchone()[0]


# --------------------------------------------------------------------------- FORECASTS (Module 8)
def save_forecast(user_id, category_id, month, amount, lower, upper):
    with get_conn() as c:
        ex = c.execute("SELECT id FROM forecasts WHERE user_id=? AND category_id=? AND forecast_month=?"
                       " AND is_deleted=0", (user_id, category_id, month)).fetchone()
        if ex:
            _update(c, "forecasts", ex["id"], {"forecast_amount": float(amount), "confidence_lower": float(lower),
                                               "confidence_upper": float(upper), "generated_at": now()}, user_id)
            return ex["id"]
        fid, ts = new_id(), now()
        _insert(c, "forecasts", dict(id=fid, user_id=user_id, category_id=category_id, forecast_month=month,
                                     forecast_amount=float(amount), confidence_lower=float(lower),
                                     confidence_upper=float(upper), generated_at=ts, updated_at=ts,
                                     is_deleted=0), user_id)
        return fid


def get_forecasts(user_id, month=None):
    q = ("SELECT f.*, c.category_name FROM forecasts f JOIN categories c ON c.id=f.category_id"
         " WHERE f.is_deleted=0 AND f.user_id=?")
    args = [user_id]
    if month:
        q += " AND f.forecast_month=?"; args.append(month)
    q += " ORDER BY f.forecast_month DESC, c.category_name"
    with get_conn() as c:
        return _rows(c.execute(q, args))


def delete_forecast(forecast_id, user_id):
    with get_conn() as c:
        _update(c, "forecasts", forecast_id, {"is_deleted": 1}, user_id, "delete")


# --------------------------------------------------------------------------- SYNC support (Module 9)
def get_sync_entries(user_id, status=None):
    q = "SELECT * FROM sync_log WHERE user_id=?"
    args = [user_id]
    if status:
        q += " AND sync_status=?"; args.append(status)
    q += " ORDER BY local_updated_at DESC"
    with get_conn() as c:
        return _rows(c.execute(q, args))


def sync_counts(user_id):
    with get_conn() as c:
        rows = c.execute("SELECT sync_status, COUNT(*) n FROM sync_log WHERE user_id=? GROUP BY sync_status",
                         (user_id,)).fetchall()
        last = c.execute("SELECT MAX(synced_at) FROM sync_log WHERE user_id=?", (user_id,)).fetchone()[0]
    d = {"pending": 0, "synced": 0, "conflict": 0}
    for r in rows:
        d[r["sync_status"]] = r["n"]
    d["last_sync"] = last
    return d


def get_row(table, record_id):
    if table not in SYNC_TABLES:
        raise ValueError(table)
    with get_conn() as c:
        return _row(c.execute(f"SELECT * FROM {table} WHERE id=?", (record_id,)))


def list_rows(table, user_id):
    """All rows (incl. soft-deleted) that belong to the user - used by the sync manager."""
    if table not in SYNC_TABLES:
        raise ValueError(table)
    with get_conn() as c:
        if table == "users":
            return _rows(c.execute("SELECT * FROM users WHERE id=?", (user_id,)))
        return _rows(c.execute(f"SELECT * FROM {table} WHERE user_id=?", (user_id,)))


def apply_remote_row(table, row: dict):
    """Write a remote record into the local table WITHOUT creating a pending sync entry."""
    if table not in SYNC_TABLES:
        raise ValueError(table)
    with get_conn() as c:
        cols = [r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()]
        data = {k: row.get(k) for k in cols}
        names = ", ".join(cols)
        marks = ", ".join("?" for _ in cols)
        updates = ", ".join(f"{k}=excluded.{k}" for k in cols if k != "id")
        c.execute(f"INSERT INTO {table} ({names}) VALUES ({marks}) ON CONFLICT(id) DO UPDATE SET {updates}",
                  [data[k] for k in cols])


def mark_sync_entry(user_id, table, record_id, status, remote_updated_at=None, resolved_value=None,
                    operation=None, local_updated_at=None):
    """Create/update the sync_log entry of a record after push/pull/conflict handling."""
    ts = now()
    with get_conn() as c:
        row = c.execute("SELECT id, operation, local_updated_at FROM sync_log WHERE table_name=? AND record_id=?",
                        (table, record_id)).fetchone()
        rv = json.dumps(resolved_value) if resolved_value is not None else None
        if row is None:
            c.execute("INSERT INTO sync_log (id, user_id, table_name, record_id, operation, sync_status,"
                      " local_updated_at, remote_updated_at, resolved_value, synced_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (new_id(), user_id, table, record_id, operation or "update", status,
                       local_updated_at or ts, remote_updated_at, rv, ts))
        else:
            c.execute("UPDATE sync_log SET sync_status=?, remote_updated_at=?, resolved_value=?, synced_at=?,"
                      " local_updated_at=COALESCE(?, local_updated_at) WHERE id=?",
                      (status, remote_updated_at, rv, ts, local_updated_at, row["id"]))


# --------------------------------------------------------------------------- TRANSACTION ITEMS (item-level records)
def add_item(user_id, transaction_id, receipt_id, name, amount, category_id):
    iid, ts = new_id(), now()
    with get_conn() as c:
        _insert(c, "transaction_items", dict(id=iid, user_id=user_id, transaction_id=transaction_id,
                                             receipt_id=receipt_id, item_name=name.strip()[:80], amount=float(amount),
                                             category_id=category_id, created_at=ts, updated_at=ts, is_deleted=0), user_id)
    return iid


def get_items(user_id, transaction_id=None):
    q = ("SELECT i.*, c.category_name FROM transaction_items i JOIN categories c ON c.id=i.category_id"
         " WHERE i.is_deleted=0 AND i.user_id=?")
    args = [user_id]
    if transaction_id:
        q += " AND i.transaction_id=?"
        args.append(transaction_id)
    q += " ORDER BY i.created_at"
    with get_conn() as c:
        return _rows(c.execute(q, args))


# --------------------------------------------------------------------------- ADMIN DASHBOARD (patch #21)
def activity_by_month():
    """({'YYYY-MM': transactions}, {'YYYY-MM': receipts}) over all users."""
    with get_conn() as c:
        tx = {r[0]: r[1] for r in c.execute(
            "SELECT substr(date,1,7), COUNT(*) FROM transactions WHERE is_deleted=0 GROUP BY 1")}
        rc = {r[0]: r[1] for r in c.execute(
            "SELECT substr(upload_date,1,7), COUNT(*) FROM receipts WHERE is_deleted=0 GROUP BY 1")}
    return tx, rc


def ocr_engine_counts():
    with get_conn() as c:
        return {r[0]: r[1] for r in c.execute(
            "SELECT COALESCE(ocr_engine,'unknown'), COUNT(*) FROM receipts WHERE is_deleted=0 GROUP BY 1")}


def recent_alerts_all(limit=5):
    with get_conn() as c:
        return _rows(c.execute("""
            SELECT a.*, t.merchant, t.amount, t.date, c.category_name, u.username
            FROM anomaly_alerts a JOIN transactions t ON t.id=a.transaction_id
            JOIN categories c ON c.id=t.category_id JOIN users u ON u.id=a.user_id
            WHERE a.is_deleted=0 AND t.is_deleted=0 AND a.status='active'
            ORDER BY a.created_at DESC LIMIT ?""", (limit,)))
