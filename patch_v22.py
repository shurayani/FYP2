"""One-time patch #22: Transaction Oversight becomes a REVIEW QUEUE, so the admin never has to check every
transaction one by one.
  * 'Show' choice: All transactions / Unusual only (|Z| > 2) / Highest |Z| first / Largest amounts first
  * three totals above the table: transactions shown, unusual ones, ones that already have an alert
  * the table gets a Z column and the alert status (active / reviewed / dismissed)
  * the 'Flag a suspicious transaction' list follows the same order (most suspicious first)
Run once from the project folder:   python patch_v22.py      then commit + push + Reboot app."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


def f_db(s):
    if "def alert_status_map" in s:
        return s
    return s + '''

def alert_status_map():
    """{transaction_id: alert status} for every alert that is not deleted (admin review queue, patch #22)."""
    with get_conn() as c:
        return {r[0]: r[1] for r in c.execute("SELECT transaction_id, status FROM anomaly_alerts WHERE is_deleted=0")}
'''


edit("src/db_manager.py", f_db)


def f_admin(s):
    if "adm_focus" in s:
        return s
    s = swap(s, '''    rows = db.get_transactions(uid_filter, start=s, end=e, category_id=None if c_sel == t("All") else cats[c_sel],
                               max_amount=max_amt if max_amt > 0 else None)
''', '''    rows = db.get_transactions(uid_filter, start=s, end=e, category_id=None if c_sel == t("All") else cats[c_sel],
                               max_amount=max_amt if max_amt > 0 else None)
    # ---- review queue (patch #22): the most suspicious transactions first, not one by one
    from utils.config import ANOMALY_Z_THRESHOLD
    opt_all, opt_unusual, opt_z, opt_amt = (t("All transactions"), t("Unusual only (|Z| > 2)"),
                                            t("Highest |Z| first"), t("Largest amounts first"))
    focus = st.radio(t("Show"), [opt_all, opt_unusual, opt_z, opt_amt], horizontal=True, key="adm_focus")
    for r_ in rows:
        r_["_absz"] = abs(r_["z_score"] or 0.0)
    if focus == opt_unusual:
        rows = sorted([r_ for r_ in rows if r_["_absz"] > ANOMALY_Z_THRESHOLD], key=lambda r_: -r_["_absz"])
    elif focus == opt_z:
        rows = sorted(rows, key=lambda r_: -r_["_absz"])
    elif focus == opt_amt:
        rows = sorted(rows, key=lambda r_: -r_["amount"])
    alert_map = db.alert_status_map()
    q1, q2, q3 = st.columns(3)
    q1.metric(t("Transactions shown"), len(rows))
    q2.metric(t("Unusual (|Z| > 2)"), sum(1 for r_ in rows if r_["_absz"] > ANOMALY_Z_THRESHOLD))
    q3.metric(t("Already have an alert"), sum(1 for r_ in rows if r_["id"] in alert_map))
''')
    s = swap(s, '''                             t("Anomaly"): df["is_anomaly"].map({1: "Yes", 0: ""})})''',
             '''                             "Z": df["z_score"].fillna(0.0).astype(float).round(2),
                             t("Anomaly"): df["is_anomaly"].map({1: "Yes", 0: ""}),
                             t("Alert"): df["id"].map(lambda i: t(alert_map[i]) if i in alert_map else "")})''')
    return s


edit("views/9_Admin_Panel.py", f_admin)


def f_i18n(s):
    if "Unusual only (|Z| > 2)" in s:
        return s
    return s + """

MS.update({
    "Show": "Tunjuk",
    "All transactions": "Semua transaksi",
    "Unusual only (|Z| > 2)": "Luar biasa sahaja (|Z| > 2)",
    "Highest |Z| first": "|Z| tertinggi dahulu",
    "Largest amounts first": "Jumlah terbesar dahulu",
    "Transactions shown": "Transaksi dipaparkan",
    "Unusual (|Z| > 2)": "Luar biasa (|Z| > 2)",
    "Already have an alert": "Sudah ada amaran",
    "Alert": "Amaran",
})
"""


edit("utils/i18n.py", f_i18n)
print("Done. Commit + push, then Reboot app.")