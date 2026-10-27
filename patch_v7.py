"""One-time patch #7 (Option C): item-level records.
  * new table  transaction_items  (item name, amount, category) - stored locally and synced to Supabase
  * OCR confirmation form (when Gemini read the items): edit every ITEM and its own category;
    the items are grouped by category into transactions automatically
  * Transactions page: 'Items' column + list of the items inside the selected transaction
Requires patches #5 and #6 first.   Run once from the project folder:   python patch_v7.py
AFTER running it, run supabase_transaction_items.sql once in the Supabase SQL editor (file is created for you)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found (did you run patches #5 and #6 first?): " + old[:70]
    return s.replace(old, new, 1)


# ============================================================ src/db_manager.py
def f_db(s):
    if "transaction_items" in s:
        return s
    s = swap(s, "CREATE TABLE IF NOT EXISTS sync_log (", '''CREATE TABLE IF NOT EXISTS transaction_items (
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
CREATE TABLE IF NOT EXISTS sync_log (''')
    s = swap(s, '"transactions",\n               "budgets"', '"transactions", "transaction_items",\n               "budgets"')
    s = swap(s, "SELECT t.*, c.category_name, u.username FROM transactions t",
             "SELECT t.*, c.category_name, u.username,\n"
             "                (SELECT COUNT(*) FROM transaction_items i WHERE i.transaction_id=t.id AND i.is_deleted=0) AS item_count\n"
             "                FROM transactions t")
    # editing a transaction's category moves its items with it
    s = swap(s, '        _update(c, "transactions", tx_id, allowed, user_id)\n',
             '        _update(c, "transactions", tx_id, allowed, user_id)\n'
             '        if "category_id" in allowed:\n'
             '            for it in _rows(c.execute("SELECT id FROM transaction_items WHERE transaction_id=? AND is_deleted=0", (tx_id,))):\n'
             '                _update(c, "transaction_items", it["id"], {"category_id": allowed["category_id"]}, user_id)\n')
    # deleting a transaction deletes its items
    s = swap(s, '        _update(c, "transactions", tx_id, {"is_deleted": 1}, user_id, "delete")\n',
             '        for it in _rows(c.execute("SELECT id FROM transaction_items WHERE transaction_id=? AND is_deleted=0", (tx_id,))):\n'
             '            _update(c, "transaction_items", it["id"], {"is_deleted": 1}, user_id, "delete")\n'
             '        _update(c, "transactions", tx_id, {"is_deleted": 1}, user_id, "delete")\n')
    # deleting a category with reassignment moves the items too
    s = swap(s, '                _update(c, "transactions", t["id"], {"category_id": reassign_to}, t["user_id"])\n',
             '                _update(c, "transactions", t["id"], {"category_id": reassign_to}, t["user_id"])\n'
             '                for it in _rows(c.execute("SELECT id FROM transaction_items WHERE transaction_id=? AND is_deleted=0", (t["id"],))):\n'
             '                    _update(c, "transaction_items", it["id"], {"category_id": reassign_to}, t["user_id"])\n')
    s += '''

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
'''
    return s


edit("src/db_manager.py", f_db)

# ============================================================ Supabase SQL file
sql = ROOT / "supabase_transaction_items.sql"
sql.write_text("""-- Run ONCE in the Supabase SQL editor (after the main schema).
create table if not exists transaction_items (
  id text primary key, user_id text not null references users(id),
  transaction_id text not null references transactions(id), receipt_id text references receipts(id),
  item_name text not null, amount double precision not null, category_id text not null references categories(id),
  created_at text not null, updated_at text not null, is_deleted integer not null default 0);
alter table transaction_items enable row level security;
create policy "ipecs_all_transaction_items" on transaction_items for all to anon, authenticated using (true) with check (true);
""", encoding="utf-8")
print("created supabase_transaction_items.sql")


# ============================================================ utils/i18n.py
def f_i18n(s):
    if "Ignore the items" in s:
        return s
    return s + '''

MS.update({
    "Gemini read the items on this receipt. Each item has its own category - please review them.":
        "Gemini membaca barang pada resit ini. Setiap barang ada kategori sendiri - sila semak.",
    "Ignore the items and save as a single transaction": "Abaikan barang dan simpan sebagai satu transaksi",
    "Add at least one item.": "Tambah sekurang-kurangnya satu barang.",
    "Item": "Barang",
    "Transactions that will be saved": "Transaksi yang akan disimpan",
    "The items differ from the receipt total by {d} (tax, rounding or discount). It is added to {c}.":
        "Barang berbeza daripada jumlah resit sebanyak {d} (cukai, pembundaran atau diskaun). Ia ditambah kepada {c}.",
    "The items add up to {s} but the receipt total is {tot}. Fix the items or the total.":
        "Jumlah barang ialah {s} tetapi jumlah resit ialah {tot}. Betulkan barang atau jumlah.",
    "Please fix the items so they add up to the receipt total.": "Sila betulkan barang supaya sepadan dengan jumlah resit.",
    "{n} transactions saved with {m} items.": "{n} transaksi disimpan dengan {m} barang.",
    "Items": "Barang",
    "Items on this transaction": "Barang dalam transaksi ini",
})
'''


edit("utils/i18n.py", f_i18n)


# ============================================================ pages/2_Receipts.py
def f_receipts(s):
    if "def item_editor" in s:
        return s
    marker = "# ------------------------------------------------------------------------- OCR upload"
    func = '''def item_editor(key, items, total, default_label):
    """Item-level editor: one row per purchased item, each with its own category.
    Returns (item_rows, groups, ok): item_rows = [(name, amount, category_label)], groups = [(category_label, amount)]
    (items grouped by category; a small tax/rounding/discount difference is added to the biggest group)."""
    base = pd.DataFrame({
        "item": [i["name"] or "-" for i in items],
        "amount": [i["amount"] for i in items],
        "category": [ui.cat_label(i["category"]) if i["category"] and ui.cat_label(i["category"]) in cats else default_label
                     for i in items]})
    edited = st.data_editor(
        base, num_rows="dynamic", hide_index=True, width="stretch", key=f"{key}_items",
        column_config={
            "item": st.column_config.TextColumn(t("Item"), required=True),
            "amount": st.column_config.NumberColumn(t("Amount (RM)"), min_value=0.01, step=0.10, format="%.2f", required=True),
            "category": st.column_config.SelectboxColumn(t("Category"), options=labels, required=True),
        })
    item_rows = [(str(r["item"]).strip(), round(float(r["amount"]), 2), r["category"]) for _, r in edited.iterrows()
                 if pd.notna(r["item"]) and pd.notna(r["amount"]) and pd.notna(r["category"])
                 and float(r["amount"]) > 0 and str(r["item"]).strip()]
    if not item_rows:
        st.warning(t("Add at least one item."))
        return [], [], False
    groups = {}
    for _, amt, label in item_rows:
        groups[label] = round(groups.get(label, 0.0) + amt, 2)
    diff = round(float(total) - round(sum(groups.values()), 2), 2)
    ok = True
    if abs(diff) > 0.005:
        if total > 0 and abs(diff) / total <= 0.25:
            big = max(groups, key=groups.get)
            groups[big] = round(groups[big] + diff, 2)
            ok = groups[big] > 0
            st.caption(t("The items differ from the receipt total by {d} (tax, rounding or discount). It is added to {c}.",
                         d=ui.money(diff), c=big))
        else:
            ok = False
            st.warning(t("The items add up to {s} but the receipt total is {tot}. Fix the items or the total.",
                         s=ui.money(sum(groups.values())), tot=ui.money(total)))
    if ok:
        st.markdown(f"**{t('Transactions that will be saved')}**")
        st.dataframe(pd.DataFrame({t("Category"): list(groups.keys()), "RM": list(groups.values())}),
                     hide_index=True, width="stretch")
    return item_rows, list(groups.items()), ok


'''
    s = swap(s, marker, func + marker)

    a = s.index('        sug = res.get("suggestion")\n')
    b = s.index('    elif st.session_state.get("flash_ocr"):')
    region = '''        sug = res.get("suggestion")
        items = res.get("items") or []
        if items:
            st.info(t("Gemini read the items on this receipt. Each item has its own category - please review them."))
        st.caption(t("Please check and correct the values before saving."))

        merchant = st.text_input(t("Merchant"), value=res["merchant"], key=f"cf_m_{k}")
        c1, c2 = st.columns(2)
        tx_date = c1.date_input(t("Date"), value=res["date"], key=f"cf_d_{k}")
        amount = c2.number_input(t("Total amount (RM)"), min_value=0.0, value=float(res["amount"]), step=0.10,
                                 format="%.2f", key=f"cf_a_{k}")
        default_label = id_to_label.get(res["category_id"], labels[0])
        use_items = bool(items) and not st.checkbox(t("Ignore the items and save as a single transaction"), key=f"cf_ign_{k}")
        rows, split_ok, cat_label = None, True, None
        if use_items:
            item_rows, groups, items_ok = item_editor(f"cf_{k}", items, amount, default_label)
        else:
            initial = None
            if sug and abs(amount - float(res["amount"])) < 0.005:      # only while the total is unchanged
                initial = [(ui.cat_label(c), a) for c, a in sug["rows"] if ui.cat_label(c) in cats]
            rows, split_ok = split_section(f"cf_{k}", amount, default_label, initial)
            if rows is None:
                cat_label = st.selectbox(t("Category"), labels, index=_category_index(res["category_id"]), key=f"cf_c_{k}")
        c3, c4 = st.columns(2)
        save = c3.button(t("Confirm and save"), type="primary", key=f"cf_save_{k}")
        cancel = c4.button(t("Discard"), key=f"cf_cancel_{k}")

        if save:
            if not merchant.strip() or amount <= 0:
                st.error(t("Merchant and a positive amount are required."))
            elif use_items and not items_ok:
                st.error(t("Please fix the items so they add up to the receipt total."))
            elif not use_items and rows is not None and not split_ok:
                st.error(t("The split amounts must add up exactly to the total."))
            else:
                rel = receipt_manager.save_image(uid, res["file_name"], res["data"])
                rid = db.add_receipt(uid, rel, res["file_name"], res["raw_text"], res["engine"])
                if use_items:
                    tx_ids = {}
                    for label, amt in groups:
                        tx_ids[label] = db.add_transaction(uid, merchant, tx_date, amt, cats[label],
                                                           is_manual=False, receipt_id=rid)
                    for name, amt, label in item_rows:
                        db.add_item(uid, tx_ids[label], rid, name, amt, cats[label])
                    msg = t("{n} transactions saved with {m} items.", n=len(groups), m=len(item_rows))
                else:
                    parts = rows if rows is not None else [(cat_label, amount)]
                    for label, amt in parts:
                        db.add_transaction(uid, merchant, tx_date, amt, cats[label], is_manual=False, receipt_id=rid)
                    msg = (t("{n} transactions saved.", n=len(parts)) if len(parts) > 1 else t("Transaction saved."))
                analytics.detect_anomalies(uid)
                st.session_state.pop("ocr_result", None)
                st.session_state["flash_ocr"] = msg
                st.rerun()
        if cancel:
            st.session_state.pop("ocr_result", None)
            st.rerun()
'''
    return s[:a] + region + s[b:]


edit("pages/2_Receipts.py", f_receipts)


# ============================================================ pages/3_Transactions.py
def f_tx(s):
    if "Items on this transaction" in s:
        return s
    s = swap(s, '        t("Source"): df["is_manual"].map({1: t("Manual"), 0: "OCR"}),\n',
             '        t("Source"): df["is_manual"].map({1: t("Manual"), 0: "OCR"}),\n'
             '        t("Items"): df["item_count"],\n')
    s += '''

# ------------------------------------------------------------------ items inside the selected transaction
if rows:
    its = db.get_items(uid, transaction_id=r["id"])
    if its:
        st.subheader(t("Items on this transaction"))
        st.dataframe(pd.DataFrame({t("Item"): [i["item_name"] for i in its], "RM": [round(i["amount"], 2) for i in its],
                                   t("Category"): [ui.cat_label(i["category_name"]) for i in its]}),
                     width="stretch", hide_index=True)
'''
    return s


edit("pages/3_Transactions.py", f_tx)
print("Done. Restart Streamlit, then run supabase_transaction_items.sql in Supabase.")