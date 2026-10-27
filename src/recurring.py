"""Recurring bills (patch #23): REMINDERS, never automatic transactions.

Every month IPECS reminds the user of each active bill (from 3 days before its day of the month). The user
then confirms it (a transaction is added), changes this month's amount (optionally for the following months
too), or skips the month. A bill can be paused (e.g. a cancelled subscription) and resumed later."""
import calendar
import statistics
from datetime import date, timedelta

import pandas as pd

from src import db_manager as db

REMIND_DAYS_BEFORE = 3


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def due_date(bill, today: date) -> date:
    """The bill's date in today's month (day 31 becomes the last day of a shorter month)."""
    last = calendar.monthrange(today.year, today.month)[1]
    return date(today.year, today.month, min(int(bill["day_of_month"]), last))


def due_bills(user_id, today: date = None):
    """Active bills not yet confirmed or skipped this month whose day is within REMIND_DAYS_BEFORE days."""
    today = today or date.today()
    out = []
    for b in db.get_bills(user_id):
        if b["status"] != "active" or b["last_handled_month"] == month_key(today):
            continue
        d = due_date(b, today)
        if (d - today).days <= REMIND_DAYS_BEFORE:
            out.append({**b, "due": d, "overdue": d < today})
    return sorted(out, key=lambda b: b["due"])


def confirm(bill, user_id, amount=None, keep_amount=False, today: date = None):
    """Add this month's payment as a transaction. amount = this month's amount if it differs;
    keep_amount = also use it for the following months."""
    today = today or date.today()
    amt = float(amount if amount is not None else bill["amount"])
    tid = db.add_transaction(user_id, bill["name"], due_date(bill, today), amt, bill["category_id"], is_manual=True)
    fields = {"last_handled_month": month_key(today)}
    if keep_amount and abs(amt - float(bill["amount"])) > 0.005:
        fields["amount"] = amt
    db.update_bill(bill["id"], user_id, **fields)
    return tid


def skip(bill, user_id, today: date = None):
    db.update_bill(bill["id"], user_id, last_handled_month=month_key(today or date.today()))


def suggestions(user_id, today: date = None, months_back: int = 4, max_items: int = 5):
    """Merchants paid in at least 3 of the last `months_back` complete months with a similar amount
    (within 15 % of the typical amount) that are not recurring bills yet."""
    today = today or date.today()
    first = date(today.year, today.month, 1)
    y, m = first.year, first.month - months_back
    while m <= 0:
        y, m = y - 1, m + 12
    start = date(y, m, 1)
    rows = db.get_transactions(user_id, start=start, end=first - timedelta(days=1))
    if not rows:
        return []
    have = {b["name"].strip().lower() for b in db.get_bills(user_id)}
    df = pd.DataFrame(rows)
    df["key"] = df["merchant"].str.strip().str.lower()
    df["month"] = df["date"].str[:7]
    out = []
    for key, g in df.groupby("key"):
        if key in have or g["month"].nunique() < 3:
            continue
        monthly = g.groupby("month")["amount"].sum()
        typical = statistics.median(monthly.values)
        if typical <= 0 or any(abs(v - typical) / typical > 0.15 for v in monthly.values):
            continue
        out.append({"name": g["merchant"].iloc[0], "amount": round(float(typical), 2),
                    "category_id": g["category_id"].mode().iloc[0], "category_name": g["category_name"].mode().iloc[0],
                    "day_of_month": int(statistics.median(int(d[8:10]) for d in g["date"])),
                    "months": int(g["month"].nunique())})
    return sorted(out, key=lambda s: (-s["months"], -s["amount"]))[:max_items]
