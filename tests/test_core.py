"""Run with:  python -m pytest -q   (or  python tests/test_core.py)
Covers the logic the report evaluates: parsing, classifier, Z-score rule, budgets, reports, forecasts,
offline change tracking and last-write-wins sync (against an in-memory fake Supabase)."""
import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import analytics, auth, classifier, db_manager as db, forecast, preprocessor, sync_manager  # noqa: E402


def fresh_db():
    db.DB_PATH = Path(tempfile.mkdtemp()) / "test.db"
    auth.init()


def test_parser():
    text = "TESCO EXTRA\nTel 03-1234\nDate: 05/09/2026 14:22\nSUBTOTAL 40.00\nJUMLAH  RM 42.50\nCASH 50.00"
    f = preprocessor.parse_fields(text)
    assert f["merchant"] == "TESCO EXTRA" and f["amount"] == 42.50 and f["date"] == date(2026, 9, 5)
    assert preprocessor.parse_date("3 Oct 2026") == date(2026, 10, 3)
    v = preprocessor.validate_structured({"merchant": "KFC", "date": "2026-08-01", "amount": "RM 12.90"})
    assert v["amount"] == 12.9 and v["complete"]


def test_classifier():
    assert classifier.predict_category_name("KFC Damansara") == "Food and Beverage"
    assert classifier.predict_category_name("Petronas Penampang") == "Transport"
    assert classifier.predict_category_name("Guardian Pharmacy") == "Health"


def test_auth_and_isolation():
    fresh_db()
    assert auth.login("admin", "admin123")[0]["role"] == "admin"
    ok, _ = auth.register("alice", "alice@x.com", "secret1", "secret1")
    assert ok
    assert not auth.register("alice", "other@x.com", "secret1", "secret1")[0]
    u, _ = auth.login("alice", "secret1")
    assert u and u["role"] == "user"
    assert auth.login("alice", "wrong")[0] is None
    auth.deactivate_account(u["id"])
    assert auth.login("alice", "secret1")[0] is None
    assert len(db.get_categories(u["id"])) == 7


def test_zscore_budget_report_forecast():
    fresh_db()
    auth.register("bob", "bob@x.com", "secret1", "secret1")
    uid = auth.login("bob", "secret1")[0]["id"]
    food = db.category_uuid("Food and Beverage")
    today = date.today()
    for i in range(1, 200):
        db.add_transaction(uid, "KFC", today - timedelta(days=i), 10 + (i % 5), food)
    big = db.add_transaction(uid, "KFC", today, 200.0, food)
    res = analytics.detect_anomalies(uid)
    assert res["flagged"] >= 1
    alert = db.get_alert_for_transaction(big)
    assert alert and abs(alert["z_score"]) > 2.0
    # Z-score of a flat category is 0 -> never flagged
    m = analytics.month_str(today)
    db.upsert_budget(uid, food, m, 300)
    bva = analytics.budget_vs_actual(uid, m)
    assert len(bva) == 1 and bva.iloc[0]["actual"] > 0
    rep = analytics.build_report(uid, m)
    assert rep["total"] > 0 and rep["categories"][0]["budget"] == 300
    db.save_report(uid, m, rep)
    db.save_report(uid, m, rep)                     # regenerate keeps one report
    assert len(db.get_reports(uid)) == 1
    out = forecast.generate_forecasts(uid)
    assert out["saved"] == 1
    f = db.get_forecasts(uid, forecast.target_month())[0]
    assert f["confidence_lower"] <= f["forecast_amount"] <= f["confidence_upper"]
    # soft delete + pending sync log
    db.delete_transaction(big, uid)
    assert big not in [t["id"] for t in db.get_transactions(uid)]
    assert db.sync_counts(uid)["pending"] > 0


class FakeTable:
    def __init__(self, store, name):
        self.store, self.name, self.f, self.lim = store, name, [], None

    def select(self, *_): return self
    def eq(self, k, v): self.f.append((k, v)); return self
    def limit(self, n): self.lim = n; return self
    def upsert(self, row): self.row = row; self._op = "up"; return self

    def execute(self):
        tbl = self.store.setdefault(self.name, {})
        if getattr(self, "_op", None) == "up":
            tbl[self.row["id"]] = dict(self.row)
            return type("R", (), {"data": [self.row]})
        rows = [r for r in tbl.values() if all(r.get(k) == v for k, v in self.f)]
        return type("R", (), {"data": rows[: self.lim] if self.lim else rows})


class FakeClient:
    def __init__(self): self.store = {}
    def table(self, name): return FakeTable(self.store, name)


def test_sync_lww():
    fresh_db()
    auth.register("cara", "cara@x.com", "secret1", "secret1")
    uid = auth.login("cara", "secret1")[0]["id"]
    fake = FakeClient()
    sync_manager.get_client = lambda: fake
    sync_manager.is_configured = lambda: True
    sync_manager.check_connection = lambda: (True, "ok")
    food = db.category_uuid("Food and Beverage")
    tid = db.add_transaction(uid, "Old Town", date.today(), 12.0, food)
    assert db.sync_counts(uid)["pending"] >= 2             # user + transaction logged offline
    r = sync_manager.sync_now(uid)
    assert r["ok"] and db.sync_counts(uid)["pending"] == 0 and tid in fake.store["transactions"]
    # edit on both sides -> conflict, later updated_at wins
    db.update_transaction(tid, uid, merchant="Local Edit")
    remote = dict(fake.store["transactions"][tid]); remote["merchant"] = "Remote Edit"
    remote["updated_at"] = "2999-01-01T00:00:00.000+00:00"
    fake.store["transactions"][tid] = remote
    r = sync_manager.sync_now(uid)
    assert len(r["conflicts"]) == 1 and r["conflicts"][0]["kept"] == "remote"
    assert db.get_transaction(tid)["merchant"] == "Remote Edit"
    st = sync_manager.status(uid)
    assert st["conflict_count"] == 1 and st["conflicts"][0]["kept"] == "remote"
    # offline delete reaches the server as soft-delete
    db.delete_transaction(tid, uid)
    sync_manager.sync_now(uid)
    assert fake.store["transactions"][tid]["is_deleted"] == 1
    # remote-only record is pulled
    rid = "11111111-1111-1111-1111-111111111111"
    fake.store.setdefault("budgets", {})[rid] = dict(id=rid, user_id=uid, category_id=food, budget_month="2026-10",
        budget_amount=99.0, created_at="2026-10-01T00:00:00.000+00:00", updated_at="2026-10-02T00:00:00.000+00:00", is_deleted=0)
    r = sync_manager.sync_now(uid)
    assert r["pulled"] >= 1 and db.get_row("budgets", rid)["budget_amount"] == 99.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)
