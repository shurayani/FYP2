"""One-time patch #26:
  1. BUG FIX - 'Select a transaction' lost transactions with the same date, merchant and amount (e.g. two NINSO
     transactions of RM 5.04 from one receipt). The list now keeps every transaction and also shows its
     category and number of items. Same fix for 'Flag a suspicious transaction' in the Admin Panel.
  2. MOVE ONE ITEM to another category (Transactions > History, under 'Items on this transaction'): the item moves to
     that category's transaction for the same receipt (created if needed); both amounts are updated.
  3. PHOTOS THAT ARE NOT RECEIPTS: Gemini also says whether the photo is a receipt; if not, IPECS asks for a
     photo of a receipt instead of showing an error. A note under the upload says to use receipts only.
  4. GEMINI BUSY (HTTP 503 'high demand'): IPECS waits 1.5 s and tries again, then tries the optional backup model
     GEMINI_FALLBACK_MODEL (set it in .env / Streamlit secrets, e.g. gemini-3.5-flash-lite).
  5. DASHBOARD: every section sits in its own white box; the receipt, budget, alerts, transactions and forecast
     cards open their page when clicked (the 'View all' links stay).
Run once from the project folder:   python patch_v26.py      then commit + push + Reboot app."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


# ============================================================ 1 + 2. Transactions page
def f_tx(s):
    if "_tx_label" in s:
        return s
    s = swap(s, '''        opts = {f"{r['date']} · {r['merchant']} · RM {r['amount']:.2f}": r for r in rows}
        choice = st.selectbox(t("Select a transaction"), list(opts.keys()))
        r = opts[choice]
''', '''        by_id = {r_["id"]: r_ for r_ in rows}            # keyed by id: same date + shop + amount no longer collide

        def _tx_label(i):
            r_ = by_id[i]
            extra = f" · {r_['item_count']} {t('items')}" if r_.get("item_count") else ""
            return f"{r_['date']} · {r_['merchant']} · {ui.cat_label(r_['category_name'])} · RM {r_['amount']:.2f}{extra}"

        r = by_id[st.selectbox(t("Select a transaction"), list(by_id.keys()), format_func=_tx_label)]
''')
    s = swap(s, '''            if abs(sum(i["amount"] for i in its) - float(r["amount"])) > 0.005:
                st.caption(t("Item prices are shown before discounts and fees. The transaction amount is what you paid."))
''', '''            if abs(sum(i["amount"] for i in its) - float(r["amount"])) > 0.005:
                st.caption(t("Item prices are shown before discounts and fees. The transaction amount is what you paid."))
            st.markdown(f"**{t('Move an item to another category')}**")
            it_by_id = {i["id"]: i for i in its}
            others = [l_ for l_ in labels if cats[l_] != r["category_id"]]
            with st.form(f"move_item_{r['id']}"):
                mc1, mc2 = st.columns(2)
                it_id = mc1.selectbox(t("Item"), list(it_by_id.keys()),
                                      format_func=lambda i: f"{it_by_id[i]['item_name']} · RM {it_by_id[i]['amount']:.2f}")
                new_cat = mc2.selectbox(t("Move to"), others)
                go_move = st.form_submit_button(t("Move item"))
            if go_move and new_cat:
                db.move_item(uid, it_id, cats[new_cat])
                analytics.detect_anomalies(uid)
                st.session_state["tx_flash"] = t("Moved {item} to {cat}.", item=it_by_id[it_id]["item_name"], cat=new_cat)
                st.rerun()
''')
    s = swap(s, 'if _view == "history":\n',
             'if _view == "history":\n    if st.session_state.get("tx_flash"):\n'
             '        st.success(st.session_state.pop("tx_flash"))\n')
    return s


edit("views/3_Transactions.py", f_tx)


def f_admin(s):
    if "_flag_label" in s:
        return s
    return swap(s, '''        opts = {f"{r['username']} · {r['date']} · {r['merchant']} · RM {r['amount']:.2f}": r for r in rows[:200]}
        r = opts[st.selectbox(t("Select a transaction"), list(opts.keys()))]
''', '''        flag_by_id = {r_["id"]: r_ for r_ in rows[:200]}

        def _flag_label(i):
            r_ = flag_by_id[i]
            return (f"{r_['username']} · {r_['date']} · {r_['merchant']} · {ui.cat_label(r_['category_name'])} · "
                    f"RM {r_['amount']:.2f}")

        r = flag_by_id[st.selectbox(t("Select a transaction"), list(flag_by_id.keys()), format_func=_flag_label)]
''')


edit("views/9_Admin_Panel.py", f_admin)
print("transactions + admin ok")


def f_db(s):
    if "def move_item" in s:
        return s
    return s + '''

# --------------------------------------------------------------------------- MOVE ONE ITEM (patch #26)
def move_item(user_id, item_id, new_category_id):
    """Move one receipt item to another category. It joins that category's transaction for the same receipt
    (created when there is none) and the item's share of the amount moves with it; a transaction left without
    items is removed. Returns 'same', 'recategorised', 'merged', 'moved' or None (item not found)."""
    with get_conn() as c:
        it = _row(c.execute("SELECT * FROM transaction_items WHERE id=? AND user_id=? AND is_deleted=0",
                            (item_id, user_id)))
        if not it:
            return None
        tx = _row(c.execute("SELECT * FROM transactions WHERE id=? AND is_deleted=0", (it["transaction_id"],)))
        if not tx or tx["category_id"] == new_category_id:
            return "same"
        items = _rows(c.execute("SELECT id, amount FROM transaction_items WHERE transaction_id=? AND is_deleted=0",
                                (tx["id"],)))
        sibling = None
        if tx["receipt_id"]:
            sibling = _row(c.execute(
                "SELECT * FROM transactions WHERE receipt_id=? AND category_id=? AND is_deleted=0 AND id<>? LIMIT 1",
                (tx["receipt_id"], new_category_id, tx["id"])))
        total = float(tx["amount"])
        if len(items) <= 1:                                   # the only item: the whole amount goes with it
            moved = total
        else:                                                 # its share of what was paid (discounts/fees included)
            items_sum = sum(float(i["amount"]) for i in items)
            moved = round(total * float(it["amount"]) / items_sum, 2) if items_sum > 0 else float(it["amount"])
            moved = max(0.01, min(moved, round(total - 0.01, 2)))
        if len(items) <= 1 and sibling is None:               # just change the category of this transaction
            _update(c, "transactions", tx["id"], {"category_id": new_category_id}, user_id)
            _update(c, "transaction_items", it["id"], {"category_id": new_category_id}, user_id)
            return "recategorised"
        if sibling is not None:
            target_id = sibling["id"]
            _update(c, "transactions", target_id, {"amount": round(float(sibling["amount"]) + moved, 2)}, user_id)
        else:
            target_id, ts = new_id(), now()
            _insert(c, "transactions", dict(id=target_id, user_id=user_id, receipt_id=tx["receipt_id"],
                                            merchant=tx["merchant"], date=tx["date"], amount=moved,
                                            category_id=new_category_id, is_manual=tx["is_manual"], z_score=None,
                                            is_anomaly=0, created_at=ts, updated_at=ts, is_deleted=0), user_id)
        _update(c, "transaction_items", it["id"], {"transaction_id": target_id, "category_id": new_category_id}, user_id)
        if len(items) <= 1:                                   # nothing left in the old transaction
            for a in _rows(c.execute("SELECT id FROM anomaly_alerts WHERE transaction_id=? AND is_deleted=0", (tx["id"],))):
                _update(c, "anomaly_alerts", a["id"], {"is_deleted": 1}, user_id, "delete")
            _update(c, "transactions", tx["id"], {"is_deleted": 1}, user_id, "delete")
            return "merged"
        _update(c, "transactions", tx["id"], {"amount": round(total - moved, 2)}, user_id)
        return "merged" if sibling is not None else "moved"
'''


edit("src/db_manager.py", f_db)
print("db_manager.py ok")


# ============================================================ 3 + 4. receipts that are not receipts, Gemini busy
def f_config(s):
    if "GEMINI_FALLBACK_MODEL" in s:
        return s
    return swap(s, 'GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()\n',
                'GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()\n'
                'GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "").strip()   # used when the main model is busy\n')


edit("utils/config.py", f_config)


def f_gemini(s):
    if "GEMINI_FALLBACK_MODEL" in s:
        return s
    s = swap(s, "import re\n", "import re\nimport time\n")
    s = swap(s, "from utils.config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT",
             "from utils.config import GEMINI_API_KEY, GEMINI_FALLBACK_MODEL, GEMINI_MODEL, GEMINI_TIMEOUT")
    s = swap(s, '''    try:
        r = requests.post(ENDPOINT.format(model=GEMINI_MODEL), json=body,
                          headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                          timeout=timeout or GEMINI_TIMEOUT)
    except requests.Timeout:
        raise NetworkError(f"took longer than {timeout or GEMINI_TIMEOUT:g} s")
    except requests.ConnectionError:
        raise NetworkError("could not connect to the Gemini server")
''', '''    # busy (5xx): wait and try the same model once more; still busy or out of quota: the backup model, if set
    plan = [GEMINI_MODEL, GEMINI_MODEL]
    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL:
        plan.append(GEMINI_FALLBACK_MODEL)
    r = None
    for attempt, model in enumerate(plan):
        if attempt == 1:
            if r.status_code == 429:
                continue                                  # quota: the same model again will not help
            time.sleep(1.5)
        try:
            r = requests.post(ENDPOINT.format(model=model), json=body,
                              headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
                              timeout=timeout or GEMINI_TIMEOUT)
        except requests.Timeout:
            raise NetworkError(f"took longer than {timeout or GEMINI_TIMEOUT:g} s")
        except requests.ConnectionError:
            raise NetworkError("could not connect to the Gemini server")
        if r.status_code not in (429, 500, 502, 503, 504):
            break
''')
    s = swap(s, '''    else:
        raise NetworkError(f"HTTP {r.status_code} - " + _google_message(r))
''', '''    elif r.status_code in (500, 502, 503, 504):
        raise NetworkError(f"the Gemini service is busy (HTTP {r.status_code}), please try again in a minute - "
                           + _google_message(r))
    else:
        raise NetworkError(f"HTTP {r.status_code} - " + _google_message(r))
''')
    s = swap(s, """'"merchant" (store name, string), """,
             """'"is_receipt" (true only if the image shows a shop receipt, invoice or bill; false for anything else), '
              '"merchant" (store name, string), """)
    return s


edit("utils/gemini_helper.py", f_gemini)


def f_ocr(s):
    if "class NotAReceipt" in s:
        return s
    s = swap(s, "_paddle = None\n", '''_paddle = None


class NotAReceipt(Exception):
    """The photo is not a receipt, or nothing could be read from it (the message is shown to the user)."""
''')
    s = swap(s, '''            data = gemini_helper.extract_receipt_fields(to_jpeg_bytes(img), categories)
''', '''            data = gemini_helper.extract_receipt_fields(to_jpeg_bytes(img), categories)
            if str(data.get("is_receipt")).strip().lower() == "false":
                raise NotAReceipt("This photo does not look like a receipt. Please upload or take a photo of a receipt or bill.")
''')
    s = swap(s, '''    if not paddle_available():
        reason = note''', '''    if not paddle_available() and "empty Gemini response" in note:
        raise NotAReceipt("Nothing could be read from this photo. Please take a clear, well-lit photo of the whole receipt.")
    if not paddle_available():
        reason = note''')
    return s


edit("src/ocr_module.py", f_ocr)


def f_receipts(s):
    if "NotAReceipt" in s:
        return s
    s = swap(s, '''                    except Exception as e:
                        st.session_state.pop("ocr_result", None)
                        st.error(f"{t('Extraction failed')}: {e}")
''', '''                    except ocr_module.NotAReceipt as e:
                        st.session_state.pop("ocr_result", None)
                        st.warning(t(str(e)))
                    except Exception as e:
                        st.session_state.pop("ocr_result", None)
                        st.error(f"{t('Extraction failed')}: {e}")
''')
    return swap(s, '''                if source == t("Upload file") else st.camera_input(t("Take a photo of the receipt")))
''', '''                if source == t("Upload file") else st.camera_input(t("Take a photo of the receipt")))
    st.caption(t("Use a photo of a receipt or bill only. Other photos cannot be read."))
''')


edit("views/2_Receipts.py", f_receipts)
print("OCR + Gemini ok")


# ============================================================ 5. dashboard: boxes + clickable cards
CSS = '''
/* ---------- dashboard sections in their own boxes, clickable summary cards (patch #26) */
[class*="st-key-box_"] { background:#FFFFFF; }
[class*="st-key-dlink"] { position:relative; }
[class*="st-key-dlink"] [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) {
    position:absolute; inset:0; z-index:5; margin:0; }
[class*="st-key-dlink"] [data-testid="stPageLink"], [class*="st-key-dlink"] [data-testid="stPageLink-NavLink"] {
    width:100%; height:100%; opacity:0; }
[class*="st-key-dlink"] [data-testid="stMetric"], [class*="st-key-dlink"] .meter { transition:border-color .15s ease; }
[class*="st-key-dlink"]:hover [data-testid="stMetric"], [class*="st-key-dlink"]:hover .meter { border-color:#0F7B6C; }
[class*="st-key-dlink"]:hover .slip-wrap { filter:drop-shadow(0 0 1px #0F7B6C) drop-shadow(0 10px 16px rgba(22,37,61,0.1)); }
[class*="st-key-dlink"]:has(a:focus-visible) { outline:2px solid #0F7B6C; outline-offset:3px; border-radius:12px; }
'''

USER_CARDS = '''        with st.container(key="dlink_slip"):
            st.markdown(ui.receipt_slip(ui.month_label(month), lines, total, top_cat), unsafe_allow_html=True)
            st.page_link("views/6_Reports.py", label=t("Open reports"))
    with glance_col:
        with st.container(key="dlink_budget"):
            st.markdown(ui.budget_meter(pct), unsafe_allow_html=True)
            st.page_link("views/5_Budget_Goals.py", label=t("Open budget goals"))
        with st.container(key="glance"):
            g = st.columns(3)
            with g[0]:
                with st.container(key="dlink_alerts"):
                    st.metric(t("Unresolved alerts"), len(active_alerts))
                    st.page_link("views/7_Anomaly_Alerts.py", label=t("View all alerts"))
            with g[1]:
                with st.container(key="dlink_tx"):
                    st.metric(t("Transactions recorded"), len(all_tx))
                    st.page_link("views/3_Transactions.py", label=t("All transactions"))
            with g[2]:
                with st.container(key="dlink_fc"):
                    st.metric(t("Forecast next month"), ui.money(fc_total) if fc_total is not None else "—")
                    st.page_link("views/8_Forecast.py", label=t("Open forecasts"))
'''

USER_SECTIONS = '''    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True, key="box_trend"):
            st.subheader(t("Monthly spending trend"), anchor=False)
            trend = analytics.monthly_totals(uid, 6)
            fig = px.line(trend, x="month", y="total", markers=True, labels={"month": t("Month"), "total": "RM"},
                          color_discrete_sequence=ui.CHART_COLORS)
            fig.update_layout(margin=dict(t=10, b=10))
            st.plotly_chart(fig, width="stretch")
    with c2:
        with st.container(border=True, key="box_breakdown"):
            st.subheader(f"{t('Category breakdown')} ({ui.month_label(month)})", anchor=False)
            if summary.empty:
                st.caption(t("No spending recorded this month."))
            else:
                s2 = summary.copy()
                s2["category_name"] = s2["category_name"].map(ui.cat_label)
                fig = px.pie(s2, names="category_name", values="total", hole=0.35,
                             color_discrete_sequence=ui.CHART_COLORS)
                fig.update_layout(margin=dict(t=10, b=10))
                st.plotly_chart(fig, width="stretch")

    with st.container(border=True, key="box_budget"):
        st.subheader(t("Budget progress"), anchor=False)
        if bva.empty:
            st.caption(t("No budget goals set for this month."))
            st.page_link("views/5_Budget_Goals.py", label=t("Set a budget goal"))
        else:
            b = bva.copy()
            b["category_name"] = b["category_name"].map(ui.cat_label)
            long = pd.melt(b, id_vars="category_name", value_vars=["budget", "actual"], var_name="type", value_name="RM")
            long["type"] = long["type"].map({"budget": t("Budget"), "actual": t("Spent")})
            fig = px.bar(long, x="category_name", y="RM", color="type", barmode="group",
                         labels={"category_name": t("Category"), "type": ""}, color_discrete_sequence=ui.CHART_COLORS)
            fig.update_layout(margin=dict(t=10, b=10))
            st.plotly_chart(fig, width="stretch")

    a1, a2 = st.columns(2)
    with a1:
        with st.container(border=True, key="box_alerts"):
            st.subheader(t("Anomaly alerts"), anchor=False)
            if not active_alerts:
                st.caption(t("No active anomaly alerts."))
            for a in active_alerts[:3]:
                st.warning(f"{a['merchant']} — {ui.money(a['amount'])} ({ui.cat_label(a['category_name'])}), Z = {a['z_score']:.2f}")
            st.page_link("views/7_Anomaly_Alerts.py", label=t("View all alerts"))
    with a2:
        with st.container(border=True, key="box_forecast"):
            st.subheader(f"{t('Forecast preview')} ({ui.month_label(next_month)})", anchor=False)
            if not forecasts:
                st.caption(t("No forecast yet. Open the Forecast page and press Recalculate."))
            for f in forecasts[:4]:
                st.write(f"{ui.cat_label(f['category_name'])}: **{ui.money(f['forecast_amount'])}**")
            st.page_link("views/8_Forecast.py", label=t("Open forecasts"))

    with st.container(border=True, key="box_recent"):
        st.subheader(t("Recent transactions"), anchor=False)
        if all_tx:
            recent = pd.DataFrame(all_tx[:8])[["date", "merchant", "category_name", "amount"]]
            recent["category_name"] = recent["category_name"].map(ui.cat_label)
            recent.columns = [t("Date"), t("Merchant"), t("Category"), "RM"]
            st.dataframe(recent, width="stretch", hide_index=True)
        else:
            st.caption(t("No transactions yet."))
        st.page_link("views/3_Transactions.py", label=t("All transactions"))

    with st.container(border=True, key="box_insights"):
        st.subheader(t("Financial insights"), anchor=False)
        for tip in analytics.insight_tips(uid):
            st.write("• " + tip)


'''


def boxed(block: str, key: str) -> str:
    """Indent an admin dashboard section one level and put it in a white box."""
    body = "".join(("    " + ln if ln.strip() else ln) for ln in block.splitlines(True))
    return f'        with st.container(border=True, key="box_{key}"):\n' + body


def f_app(s):
    if "dlink_slip" in s:
        return s
    s = swap(s, "</style>\n\"\"\"\n", CSS + "</style>\n\"\"\"\n")
    # ---- user dashboard: clickable cards
    a = s.index('        st.markdown(ui.receipt_slip(ui.month_label(month), lines, total, top_cat), unsafe_allow_html=True)\n')
    end = '            g[2].metric(t("Forecast next month"), ui.money(fc_total) if fc_total is not None else "—")\n'
    b = s.index(end) + len(end)
    s = s[:a] + USER_CARDS + s[b:]
    # ---- user dashboard: boxed sections
    a = s.index("    c1, c2 = st.columns(2)\n    with c1:\n        st.subheader(f\"{t('Monthly spending trend')}\", anchor=False)\n")
    b = s.index("# ----------------------------------------------------------------------------- navigation")
    s = s[:a] + USER_SECTIONS + s[b:]
    # ---- admin dashboard: boxed sections
    acc_a = s.index("        acc = db.classifier_accuracy()\n")
    act_a = s.index("        c1, c2 = st.columns([3, 2], gap=\"large\")\n", acc_a)
    s = s[:acc_a] + boxed(s[acc_a:act_a].rstrip("\n") + "\n", "accuracy") + "\n" + s[act_a:]
    for start, stop, key in (('            st.subheader(t("Activity per month"), anchor=False)\n', "        with c2:\n", "activity"),
                             ('            st.subheader(t("How receipts were read"), anchor=False)\n', "        c3, c4 = st.columns(2, gap=\"large\")\n", "engines"),
                             ('            st.subheader(t("Newest users"), anchor=False)\n', "        with c4:\n", "users"),
                             ('            st.subheader(t("Latest anomaly alerts"), anchor=False)\n', "        return\n", "admin_alerts")):
        a = s.index(start)
        b = s.index(stop, a)
        block = s[a:b].rstrip("\n") + "\n"
        inner = "".join(("    " + ln if ln.strip() else ln) for ln in block.splitlines(True))
        s = s[:a] + f'            with st.container(border=True, key="box_{key}"):\n' + inner + ("\n" if stop != "        return\n" else "") + s[b:]
    s = s.replace('fig = px.pie(pie, names="engine", values="n", hole=0.55)',
                  'fig = px.pie(pie, names="engine", values="n", hole=0.55, color_discrete_sequence=ui.CHART_COLORS)')
    return s


edit("app.py", f_app)
print("dashboard ok")


# ============================================================ utils/i18n.py
def f_i18n(s):
    if "Move an item to another category" in s:
        return s
    return s + """

MS.update({
    "items": "barang", "Move an item to another category": "Pindahkan satu barang ke kategori lain",
    "Move to": "Pindah ke", "Move item": "Pindahkan barang", "Moved {item} to {cat}.": "{item} dipindahkan ke {cat}.",
    "Use a photo of a receipt or bill only. Other photos cannot be read.":
        "Guna gambar resit atau bil sahaja. Gambar lain tidak dapat dibaca.",
    "This photo does not look like a receipt. Please upload or take a photo of a receipt or bill.":
        "Gambar ini tidak kelihatan seperti resit. Sila muat naik atau ambil gambar resit atau bil.",
    "Nothing could be read from this photo. Please take a clear, well-lit photo of the whole receipt.":
        "Tiada apa-apa dapat dibaca daripada gambar ini. Sila ambil gambar resit yang jelas, terang dan lengkap.",
    "Open reports": "Buka laporan", "Open budget goals": "Buka matlamat belanjawan",
    "No transactions yet.": "Belum ada transaksi.",
})
"""


edit("utils/i18n.py", f_i18n)
print("Done. Commit + push, then Reboot app (and restart Streamlit on the laptop).")