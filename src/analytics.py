"""Spending aggregation and per-category Z-score anomaly detection (Module 7, FR10, Section 5.6.7)."""
from datetime import date

import numpy as np
import pandas as pd

from src import db_manager as db
from utils.config import ANOMALY_Z_THRESHOLD, MIN_SAMPLES_FOR_ZSCORE


# ----------------------------------------------------------------- helpers
def month_str(d: date) -> str:
    return d.strftime("%Y-%m")


def month_bounds(month: str):
    y, m = map(int, month.split("-"))
    start = date(y, m, 1)
    end = date(y + (m == 12), (m % 12) + 1, 1)
    return start.isoformat(), (pd.Timestamp(end) - pd.Timedelta(days=1)).date().isoformat()


def add_months(month: str, n: int) -> str:
    y, m = map(int, month.split("-"))
    idx = y * 12 + (m - 1) + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def transactions_df(user_id, start=None, end=None) -> pd.DataFrame:
    rows = db.get_transactions(user_id, start=start, end=end)
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["id", "merchant", "date", "amount", "category_id", "category_name",
                                     "is_manual", "z_score", "is_anomaly"])
    df["date"] = pd.to_datetime(df["date"])
    return df


# ----------------------------------------------------------------- aggregation
def monthly_summary(user_id, month: str) -> pd.DataFrame:
    """Total expenditure by category for a month (grouped)."""
    s, e = month_bounds(month)
    df = transactions_df(user_id, s, e)
    if df.empty:
        return pd.DataFrame(columns=["category_id", "category_name", "total", "count"])
    g = df.groupby(["category_id", "category_name"]).agg(total=("amount", "sum"), count=("amount", "size"))
    return g.reset_index().sort_values("total", ascending=False)


def monthly_totals(user_id, months: int = 6, end_month: str = None) -> pd.DataFrame:
    end_month = end_month or month_str(date.today())
    start_month = add_months(end_month, -(months - 1))
    df = transactions_df(user_id, month_bounds(start_month)[0], month_bounds(end_month)[1])
    idx = [add_months(start_month, i) for i in range(months)]
    if df.empty:
        return pd.DataFrame({"month": idx, "total": 0.0})
    df["month"] = df["date"].dt.strftime("%Y-%m")
    t = df.groupby("month")["amount"].sum().reindex(idx, fill_value=0.0)
    return pd.DataFrame({"month": idx, "total": t.values})


def budget_vs_actual(user_id, month: str) -> pd.DataFrame:
    """One row per budgeted category: budget, actual, remaining, percent used."""
    budgets = pd.DataFrame(db.get_budgets(user_id, month))
    if budgets.empty:
        return pd.DataFrame(columns=["budget_id", "category_id", "category_name", "budget", "actual",
                                     "remaining", "pct"])
    actual = monthly_summary(user_id, month).set_index("category_id")["total"]
    out = []
    for _, b in budgets.iterrows():
        a = float(actual.get(b["category_id"], 0.0))
        bud = float(b["budget_amount"])
        out.append(dict(budget_id=b["id"], category_id=b["category_id"], category_name=b["category_name"],
                        budget=bud, actual=a, remaining=bud - a, pct=(a / bud * 100 if bud > 0 else 0.0)))
    return pd.DataFrame(out)


def progress_colour(pct: float) -> str:
    """green < 75 %, amber 75-99 %, red >= 100 % (Section 5.4.6)."""
    return "#2e9e5b" if pct < 75 else ("#f0a202" if pct < 100 else "#d64545")


# ----------------------------------------------------------------- anomaly detection
def compute_zscores(df: pd.DataFrame) -> pd.DataFrame:
    """Z = (amount - mean_category) / std_category, computed independently per category."""
    df = df.copy()
    df["z"] = 0.0
    for _, idx in df.groupby("category_id").groups.items():
        amounts = df.loc[idx, "amount"].astype(float)
        if len(amounts) < MIN_SAMPLES_FOR_ZSCORE:
            continue
        std = amounts.std(ddof=0)
        if std == 0 or np.isnan(std):
            continue
        df.loc[idx, "z"] = (amounts - amounts.mean()) / std
    return df


def detect_anomalies(user_id) -> dict:
    """Recompute Z-scores for all of the user's transactions, write z_score / is_anomaly back to
    TRANSACTIONS and create ANOMALY_ALERTS rows for new anomalies. Returns counts."""
    df = transactions_df(user_id)
    if df.empty:
        return {"flagged": 0, "new_alerts": 0}
    df = compute_zscores(df)
    new_alerts = flagged = 0
    for _, r in df.iterrows():
        z = round(float(r["z"]), 4)
        is_anom = int(abs(z) > ANOMALY_Z_THRESHOLD)
        old_z = r["z_score"] if pd.notna(r["z_score"]) else None
        if old_z is None or abs(old_z - z) > 1e-6 or int(r["is_anomaly"]) != is_anom:
            db.update_transaction(r["id"], user_id, z_score=z, is_anomaly=is_anom)
        alert = db.get_alert_for_transaction(r["id"])
        if is_anom:
            flagged += 1
            if alert is None:
                db.add_alert(user_id, r["id"], z)
                new_alerts += 1
            elif alert["status"] == "active" and abs(alert["z_score"] - z) > 1e-6:
                db.update_alert(alert["id"], user_id, z_score=z)
        elif alert is not None and alert["status"] == "active" and abs(alert["z_score"]) > ANOMALY_Z_THRESHOLD:
            db.update_alert(alert["id"], user_id, is_deleted=1)     # no longer anomalous (auto alerts only)
    return {"flagged": flagged, "new_alerts": new_alerts}


def severity(z: float) -> str:
    z = abs(z)
    return "High" if z >= 3 else "Medium"


# ----------------------------------------------------------------- report content (Module 6)
def build_report(user_id, month: str) -> dict:
    s, e = month_bounds(month)
    df = transactions_df(user_id, s, e)
    summary = monthly_summary(user_id, month)
    bva = budget_vs_actual(user_id, month)
    budget_map = {r["category_id"]: r for _, r in bva.iterrows()} if not bva.empty else {}
    total = float(df["amount"].sum()) if not df.empty else 0.0
    cats = []
    for _, r in summary.iterrows():
        b = budget_map.get(r["category_id"])
        cats.append(dict(category=r["category_name"], total=round(float(r["total"]), 2), count=int(r["count"]),
                         share=round(float(r["total"]) / total * 100, 1) if total else 0.0,
                         budget=round(float(b["budget"]), 2) if b is not None else None,
                         variance=round(float(b["budget"] - r["total"]), 2) if b is not None else None))
    # budgeted categories with no spending
    spent_ids = set(summary["category_id"]) if not summary.empty else set()
    for cid, b in budget_map.items():
        if cid not in spent_ids:
            cats.append(dict(category=b["category_name"], total=0.0, count=0, share=0.0,
                             budget=round(float(b["budget"]), 2), variance=round(float(b["budget"]), 2)))
    prev_total = float(analytics_total(user_id, add_months(month, -1)))
    change = round((total - prev_total) / prev_total * 100, 1) if prev_total else None
    days = pd.Period(month).days_in_month
    top_merchants = []
    daily = []
    if not df.empty:
        tm = df.groupby("merchant").agg(total=("amount", "sum"), visits=("amount", "size")) \
               .sort_values("total", ascending=False).head(5).reset_index()
        top_merchants = [dict(merchant=r["merchant"], total=round(float(r["total"]), 2), visits=int(r["visits"]))
                         for _, r in tm.iterrows()]
        d = df.groupby(df["date"].dt.strftime("%Y-%m-%d"))["amount"].sum()
        daily = [dict(date=k, total=round(float(v), 2)) for k, v in d.items()]
    trends = []
    if change is not None:
        trends.append(f"Spending {'rose' if change > 0 else 'fell'} {abs(change)}% compared with the previous month.")
    over = [c["category"] for c in cats if c["variance"] is not None and c["variance"] < 0]
    if over:
        trends.append("Over budget in: " + ", ".join(over) + ".")
    return dict(month=month, total=round(total, 2), transaction_count=int(len(df)),
                avg_daily=round(total / days, 2), categories=cats,
                top_category=cats[0]["category"] if cats else None, top_merchants=top_merchants,
                daily=daily, prev_total=round(prev_total, 2), change_pct=change,
                trends=trends, trend_months=monthly_totals(user_id, 6, month).to_dict("records"))


def analytics_total(user_id, month):
    s, e = month_bounds(month)
    df = transactions_df(user_id, s, e)
    return float(df["amount"].sum()) if not df.empty else 0.0


def insight_tips(user_id) -> list:
    """Simple rule-based expenditure recommendations for the dashboard insight panel."""
    month = month_str(date.today())
    tips = []
    bva = budget_vs_actual(user_id, month)
    if not bva.empty:
        for _, r in bva.iterrows():
            if r["pct"] >= 100:
                tips.append(f"You have exceeded your {r['category_name']} budget (RM {r['actual']:.2f} of RM {r['budget']:.2f}).")
            elif r["pct"] >= 75:
                tips.append(f"{r['category_name']} is at {r['pct']:.0f}% of its budget - slow down for the rest of the month.")
    s = monthly_summary(user_id, month)
    if not s.empty:
        top = s.iloc[0]
        tips.append(f"Your biggest spending category this month is {top['category_name']} (RM {top['total']:.2f}).")
    if not tips:
        tips.append("Record a few transactions and set budget goals to get personalised tips.")
    return tips[:4]
