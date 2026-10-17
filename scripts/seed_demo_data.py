"""Optional: create a demo student account with ~7 months of sample transactions, budgets and
a few outliers so every module (reports, anomaly alerts, Prophet forecasts) has data to show.

    python scripts/seed_demo_data.py          ->  login: demo / demo123
"""
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import analytics, auth, classifier, db_manager as db, forecast  # noqa: E402

random.seed(7)
auth.init()
if db.get_user_by_username("demo"):
    print("Demo user already exists (login: demo / demo123).")
    sys.exit(0)

uid = db.create_user("demo", "demo@example.com", auth.hash_password("demo123"))
MERCH = {
    "Food and Beverage": (["KFC", "Old Town White Coffee", "Kedai Kopi Ah Seng", "Starbucks", "Mamak Corner"], 6, 22),
    "Groceries": (["99 Speedmart", "Lotus's", "Mydin", "KK Mart"], 15, 60),
    "Transport": (["Grab", "Petronas", "Touch n Go Reload"], 8, 40),
    "Utilities": (["Maxis", "SESB", "Jabatan Air Sabah"], 40, 90),
    "Education": (["Popular Bookstore", "Kedai Buku UMS", "Fotostat dan Cetak"], 8, 45),
    "Health": (["Guardian Pharmacy", "Klinik Kesihatan", "Watsons"], 10, 50),
    "Entertainment": (["Netflix", "GSC Cinemas", "Spotify"], 15, 40),
}
today = date.today()
n = 0
for days_ago in range(210, 0, -1):
    d = today - timedelta(days=days_ago)
    for cat, (names, lo, hi) in MERCH.items():
        weight = {"Food and Beverage": 0.8, "Transport": 0.35, "Groceries": 0.2}.get(cat, 0.08)
        if random.random() < weight:
            db.add_transaction(uid, random.choice(names), d, round(random.uniform(lo, hi), 2),
                               db.category_uuid(cat), is_manual=random.random() < 0.4)
            n += 1
# a few clear outliers (anomaly demo)
db.add_transaction(uid, "Grab", today - timedelta(days=3), 380.0, db.category_uuid("Transport"))
db.add_transaction(uid, "Mydin", today - timedelta(days=9), 420.0, db.category_uuid("Groceries"))
m = analytics.month_str(today)
for cat, amt in (("Food and Beverage", 350), ("Groceries", 300), ("Transport", 150), ("Entertainment", 80)):
    db.upsert_budget(uid, db.category_uuid(cat), m, amt)
analytics.detect_anomalies(uid)
forecast.generate_forecasts(uid)
print(f"Seeded {n + 2} transactions for demo user. Login: demo / demo123")
