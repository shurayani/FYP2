"""One-time patch #21:
  1. DEACTIVATED ACCOUNTS: the login message now says to contact the administrator; when the admin
     deactivates or reactivates an account the change is sent to Supabase straight away (so the cloud and
     other devices see it)
  2. ADMIN DASHBOARD: activity per month (transactions + receipts), how receipts were read (Gemini / PaddleOCR),
     newest users and latest anomaly alerts, besides the four totals
  3. 'Cloud / Sync check' tab in the Admin Panel is shown only on the cloud version (IPECS_CLOUD = "1")
  4. NEW SYSTEM CATEGORY 'Shopping' (8th): clothes, shoes, electronics, accessories, household items...
       * added automatically to every local database and to Supabase (no SQL needed; a backup SQL file is created)
       * ~200 shop names added to the merchant dataset and the merchant classifier is retrained
       * the item model already knows 'Shopping' (614 items in receipt_items_dataset.csv) and now uses it
Run once from the project folder:   python patch_v21.py      then commit + push + Reboot app."""
import random
import subprocess
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


# ============================================================ 1. deactivated accounts
def f_auth(s):
    return s.replace('return None, "This account has been deactivated."',
                     'return None, "This account has been deactivated. Contact the administrator to reactivate it."')


edit("src/auth.py", f_auth)


def f_admin(s):
    if "_push_user_change" in s:
        return s
    s = swap(s, "user = ui.require_login(admin_only=True)\n", '''user = ui.require_login(admin_only=True)


def _push_user_change(user_id):
    """Send an account (de)activation to Supabase now, so the cloud and other devices see it."""
    try:
        from src import sync_manager
        if sync_manager.check_connection()[0]:
            sync_manager.push_pending(user_id, {"pushed": 0, "pulled": 0, "conflicts": []})
    except Exception:
        pass                                       # stays pending; sent at that user's next sync

''')
    s = swap(s, '''                auth.set_active(pick["id"], False)
                st.rerun()''', '''                auth.set_active(pick["id"], False)
                _push_user_change(pick["id"])
                st.rerun()''')
    s = swap(s, '''                auth.set_active(pick["id"], True)
                st.rerun()''', '''                auth.set_active(pick["id"], True)
                _push_user_change(pick["id"])
                st.rerun()''')
    # ============================================================ 3. cloud tab only on the cloud
    s = swap(s, '''tab_users, tab_sys, tab_cat, tab_tx, tab_cloud = st.tabs([t("User Management"), t("System Overview"),
                                               t("Category Management"), t("Transaction Oversight"),
                                               "Cloud / Sync check"])''', '''from src import cloud_mode as _cloud_mode
_tab_names = [t("User Management"), t("System Overview"), t("Category Management"), t("Transaction Oversight")]
if _cloud_mode.enabled():                          # diagnosis tab: cloud version only
    _tab_names.append("Cloud / Sync check")
_tabs = st.tabs(_tab_names)
tab_users, tab_sys, tab_cat, tab_tx = _tabs[:4]
tab_cloud = _tabs[4] if len(_tabs) > 4 else None''')
    a = s.index("# ------------------------------------------------------------------ cloud / sync check (patch #18)\n")
    head, block = s[:a], s[a:]
    first, rest = block.split("\n", 1)
    indented = "".join(("    " + ln if ln.strip() else ln) for ln in rest.splitlines(True))
    return head + first + "\nif tab_cloud is not None:\n" + indented


edit("views/9_Admin_Panel.py", f_admin)
print("deactivation + admin panel ok")


# ============================================================ 2. admin dashboard (db helpers + app.py)
def f_db(s):
    if "def ocr_engine_counts" in s:
        return s
    # 4. system categories: add any that are missing (so 'Shopping' reaches existing databases too)
    s = swap(s, '''    n = c.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
    if n == 0:
        ts = now()
        for name in SYSTEM_CATEGORIES:
            c.execute("INSERT INTO categories (id, category_name, is_system, user_id, updated_at, is_deleted)"
                      " VALUES (?,?,1,NULL,?,0)", (category_uuid(name), name, ts))
''', '''    ts = now()
    for name in SYSTEM_CATEGORIES:                 # also adds system categories introduced later (Shopping)
        if not c.execute("SELECT 1 FROM categories WHERE id=?", (category_uuid(name),)).fetchone():
            c.execute("INSERT INTO categories (id, category_name, is_system, user_id, updated_at, is_deleted)"
                      " VALUES (?,?,1,NULL,?,0)", (category_uuid(name), name, ts))
''')
    s = swap(s, '''SYSTEM_CATEGORIES = ["Food and Beverage", "Groceries", "Transport", "Utilities",
                     "Education", "Health", "Entertainment"]''', '''SYSTEM_CATEGORIES = ["Food and Beverage", "Groceries", "Transport", "Utilities",
                     "Education", "Health", "Entertainment", "Shopping"]''')
    return s + '''

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
'''


edit("src/db_manager.py", f_db)


def f_app(s):
    if "How receipts were read" in s:
        return s
    a = s.index('    if user["role"] == "admin":\n        st.title(t("Dashboard"))\n')
    end = '        st.page_link("views/9_Admin_Panel.py", label=t("Open Admin Panel"))\n        return\n'
    b = s.index(end) + len(end)
    return s[:a] + '''    if user["role"] == "admin":
        users = [u for u in db.list_users() if u["role"] == "user"]
        head_l, head_r = st.columns([3, 2], vertical_alignment="bottom")
        with head_l:
            st.title(t("Dashboard"), anchor=False)
            st.caption(t("System overview for the administrator."))
        with head_r:
            with st.container(key="quick_actions", horizontal=True, horizontal_alignment="right"):
                with st.container(key="qa_scan"):
                    st.page_link("views/9_Admin_Panel.py", label=t("Open Admin Panel"),
                                 icon=":material/admin_panel_settings:")
        with st.container(key="glance"):
            k = st.columns(4)
            k[0].metric(t("Total users"), len(users))
            k[1].metric(t("Total transactions"), db.count_transactions_all())
            k[2].metric(t("Receipts uploaded"), db.count_receipts_all())
            k[3].metric(t("Active anomaly alerts"), db.count_active_alerts_all())

        c1, c2 = st.columns([3, 2], gap="large")
        with c1:
            st.subheader(t("Activity per month"), anchor=False)
            tx_m, rc_m = db.activity_by_month()
            cur = analytics.month_str(date.today())
            months = [analytics.add_months(cur, -i) for i in range(5, -1, -1)]
            act = pd.DataFrame({"month": [ui.month_label(m) for m in months] * 2,
                                "count": [tx_m.get(m, 0) for m in months] + [rc_m.get(m, 0) for m in months],
                                "type": [t("Transactions")] * 6 + [t("Receipts")] * 6})
            fig = px.bar(act, x="month", y="count", color="type", barmode="group",
                         labels={"month": "", "count": "", "type": ""})
            fig.update_layout(legend=dict(orientation="h", y=1.12), margin=dict(t=10))
            st.plotly_chart(fig, width="stretch")
        with c2:
            st.subheader(t("How receipts were read"), anchor=False)
            eng = db.ocr_engine_counts()
            if not eng:
                st.caption(t("No receipts uploaded yet."))
            else:
                names = {"gemini": "Gemini AI", "paddleocr": "PaddleOCR"}
                pie = pd.DataFrame({"engine": [names.get(k_, k_) for k_ in eng], "n": list(eng.values())})
                fig = px.pie(pie, names="engine", values="n", hole=0.55)
                fig.update_layout(legend=dict(orientation="h", y=-0.1), margin=dict(t=10))
                st.plotly_chart(fig, width="stretch")

        c3, c4 = st.columns(2, gap="large")
        with c3:
            st.subheader(t("Newest users"), anchor=False)
            newest = sorted(users, key=lambda u: u["created_at"] or "", reverse=True)[:5]
            if newest:
                st.dataframe(pd.DataFrame({
                    t("Username"): [u["username"] for u in newest],
                    t("Registered"): [ui.local_time(u["created_at"], False) for u in newest],
                    t("Transactions"): [u["tx_count"] for u in newest],
                    t("Status"): [t("Active") if u["is_active"] else t("Deactivated") for u in newest]}),
                    width="stretch", hide_index=True)
            else:
                st.caption(t("No users found."))
        with c4:
            st.subheader(t("Latest anomaly alerts"), anchor=False)
            alerts = db.recent_alerts_all(5)
            if not alerts:
                st.caption(t("No active anomaly alerts."))
            for a_ in alerts:
                st.warning(f"{a_['username']} · {a_['merchant']} — {ui.money(a_['amount'])} "
                           f"({ui.cat_label(a_['category_name'])}), Z = {a_['z_score']:.2f}")
        return
''' + s[b:]


edit("app.py", f_app)
print("admin dashboard ok")


# ============================================================ 4. Shopping in Supabase (automatic) + backup SQL
def f_sync(s):
    if "ensure_remote_system_categories" in s:
        return s
    s = swap(s, "def push_pending(user_id, result):", '''_system_categories_ok = False


def ensure_remote_system_categories():
    """System categories must exist in Supabase for the foreign keys (e.g. 'Shopping', added in patch #21)."""
    global _system_categories_ok
    if _system_categories_ok:
        return
    have = {r["id"] for r in (get_client().table("categories").select("id").eq("is_system", 1).execute().data or [])}
    ts = db.now()
    for name in db.SYSTEM_CATEGORIES:
        cid = db.category_uuid(name)
        if cid not in have:
            get_client().table("categories").upsert(dict(id=cid, category_name=name, is_system=1, user_id=None,
                                                         updated_at=ts, is_deleted=0)).execute()
    _system_categories_ok = True


def push_pending(user_id, result):''')
    return swap(s, "    pending = db.get_sync_entries(user_id, \"pending\")\n",
                "    ensure_remote_system_categories()\n    pending = db.get_sync_entries(user_id, \"pending\")\n")


edit("src/sync_manager.py", f_sync)
shop_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, "ipecs.category.Shopping"))
(ROOT / "supabase_shopping_category.sql").write_text(
    "-- Patch #21: 8th system category. IPECS adds it automatically at the next sync; this file is a backup.\n"
    "insert into categories (id, category_name, is_system, user_id, updated_at, is_deleted) values\n"
    f"  ('{shop_id}','Shopping',1,null,now()::text,0)\non conflict (id) do nothing;\n", encoding="utf-8")
print("sync + supabase_shopping_category.sql ok")


# ============================================================ 4. merchant dataset + retrain
csv = ROOT / "training" / "receipt_dataset.csv"
text = csv.read_text(encoding="utf-8")
if ",Shopping\n" not in text:
    shops = ["Mr DIY", "MR. D.I.Y.", "Daiso", "Eco-Shop", "MINISO", "Uniqlo", "Padini", "Brands Outlet", "Cotton On",
             "H&M", "Zara", "Giordano", "Bata", "Vincci", "Charles & Keith", "Nike Store", "Adidas", "Sports Direct",
             "Al-Ikhsan Sports", "Skechers", "Senheng", "Harvey Norman", "Courts", "Machines", "Switch", "Samsung Store",
             "Xiaomi Store", "IKEA", "Ace Hardware", "Kaison", "Parkson", "Isetan", "Metrojaya", "Poh Kong",
             "Habib Jewels", "Shopee", "Lazada", "TikTok Shop", "Typo", "Pandora", "Bonia", "Jakel", "Kedai Pakaian Ain",
             "Kedai Kasut Sabah", "Kedai Elektronik Jaya", "Kedai Telefon Mobile Zone", "Butik Muslimah", "Hardware Lim",
             "Kedai Perabot Seri", "Watch Studio"]
    places = ["", " Cawangan", " Branch", " Mall", " Sdn Bhd", " Kota Kinabalu", " Penampang", " Imago", " Suria Sabah",
              " 1Borneo", " Damansara", " Mid Valley", " Sandakan", " Tawau", " Putatan", " Inanam"]
    rnd = random.Random(21)
    rows = set()
    for shop in shops:
        for place in rnd.sample(places, 4):
            name = shop + place
            rows.add(name.upper() if rnd.random() < 0.3 else name)
    if not text.endswith("\n"):
        text += "\n"
    csv.write_text(text + "".join(f'"{r}",Shopping\n' if "," in r else f"{r},Shopping\n" for r in sorted(rows)),
                   encoding="utf-8")
    print(f"added {len(rows)} shop names to receipt_dataset.csv")
print("retraining the merchant classifier ...")
subprocess.run([sys.executable, str(ROOT / "training" / "train_model.py")], cwd=str(ROOT), check=False)


# ============================================================ tests: 8 system categories now
def f_tests(s):
    return s.replace("assert len(db.get_categories(u[\"id\"])) == 7", "assert len(db.get_categories(u[\"id\"])) == len(db.SYSTEM_CATEGORIES)")


edit("tests/test_core.py", f_tests)


# ============================================================ utils/i18n.py
def f_i18n(s):
    if "System overview for the administrator." in s:
        return s
    return s + """

MS.update({
    "This account has been deactivated. Contact the administrator to reactivate it.":
        "Akaun ini telah dinyahaktifkan. Hubungi pentadbir untuk mengaktifkannya semula.",
    "System overview for the administrator.": "Gambaran keseluruhan sistem untuk pentadbir.",
    "Activity per month": "Aktiviti setiap bulan",
    "Receipts": "Resit",
    "How receipts were read": "Cara resit dibaca",
    "Newest users": "Pengguna terbaru",
    "Latest anomaly alerts": "Amaran anomali terkini",
    "Shopping": "Beli-belah",
})
"""


edit("utils/i18n.py", f_i18n)
print("Done. Commit + push, then Reboot app. On the laptop, restart Streamlit.")