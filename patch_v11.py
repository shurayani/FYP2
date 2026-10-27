"""One-time patch #11:
  1. DISCOUNTS / VOUCHERS / DELIVERY FEES (Foodpanda, Grab...): if the items do not add up to what you paid,
     the difference is detected automatically and spread over the categories in proportion to their amounts,
     so you no longer have to add a discount row by hand.
  2. TIMES are shown in this computer's local time (e.g. 19 Oct 2026, 5:43 PM) instead of UTC.
  3. DATES: Gemini also returns the date as printed; it is read day-first (04/10/2026 = 4 Oct 2026) and shown
     under the date field, and an unusual date (older than ~13 months or in the future) is flagged.
Requires patches up to #10.   Run once from the project folder:   python patch_v11.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


# ============================================================ utils/ui.py: local time helper
def f_ui(s):
    if "def local_time" in s:
        return s
    s = swap(s, "from datetime import date\n", "from datetime import date, datetime, timezone\n")
    s += '''

def local_time(ts, with_time=True):
    """UTC ISO timestamp (as stored in the database) -> this computer's local time, e.g. '19 Oct 2026, 5:43 PM'."""
    if not ts:
        return "—"
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone()
        day = f"{dt.day} {dt:%b %Y}"
        return f"{day}, {dt.hour % 12 or 12}:{dt:%M} {dt:%p}" if with_time else day
    except (ValueError, TypeError):
        return str(ts)
'''
    return s


edit("utils/ui.py", f_ui)


def local_time_swaps(path, pairs):
    def fn(s):
        for old, new in pairs:
            if new in s:
                continue
            s = swap(s, old, new)
        return s
    edit(path, fn)


local_time_swaps("pages/10_Sync_Status.py", [
    ('s["last_sync"][:16].replace("T", " ") if s["last_sync"] else t("Never")',
     'ui.local_time(s["last_sync"]) if s["last_sync"] else t("Never")'),
    ('[c["local_updated_at"] for c in s["conflicts"]]', '[ui.local_time(c["local_updated_at"]) for c in s["conflicts"]]'),
    ('[c["remote_updated_at"] for c in s["conflicts"]]', '[ui.local_time(c["remote_updated_at"]) for c in s["conflicts"]]'),
    ('[e["local_updated_at"] for e in shown]', '[ui.local_time(e["local_updated_at"]) for e in shown]'),
    ('[e["synced_at"] or "—" for e in shown]', '[ui.local_time(e["synced_at"]) for e in shown]'),
])
local_time_swaps("pages/1_Account.py", [("{fresh['created_at'][:10]}", "{ui.local_time(fresh['created_at'], False)}")])
local_time_swaps("pages/6_Reports.py", [("{r['generated_at'][:16].replace('T', ' ')}", "{ui.local_time(r['generated_at'])}")])
local_time_swaps("pages/9_Admin_Panel.py", [('[u["created_at"][:10] for u in shown]', '[ui.local_time(u["created_at"], False) for u in shown]')])


# ============================================================ utils/gemini_helper.py: final amount paid, printed date, no fees as items
def f_gemini(s):
    if "date_text" in s:
        return s
    s = swap(s, '\'"merchant" (store name, string), "date" (YYYY-MM-DD), "amount" (grand total paid in MYR, number), \'',
             '\'"merchant" (store name, string), "date_text" (the receipt date exactly as printed, string), \'\n'
             '              \'"date" (YYYY-MM-DD; Malaysian receipts print DD/MM/YYYY, so 04/10/2026 is 4 October 2026), \'\n'
             '              \'"amount" (the FINAL amount actually paid in MYR, after any discount or voucher, number), \'')
    s = swap(s, '"Do not list tax, rounding, discounts, payment lines or totals as items. "',
             '"Do not list tax, rounding, discounts, vouchers, promo codes, delivery fee, platform fee, service charge, "\n'
             '                "payment lines or totals as items. "')
    return s


edit("utils/gemini_helper.py", f_gemini)


# ============================================================ src/preprocessor.py: trust the printed date, read day-first
def f_pre(s):
    if "date_text" in s:
        return s
    return swap(s, '    merchant = (data.get("merchant") or "").strip() or None\n'
                   '    return finalize({"merchant": merchant, "date": parsed_date, "amount": amount})\n',
                '    date_text = str(data.get("date_text") or "").strip()\n'
                '    printed = parse_date(date_text) if date_text else None   # day-first, as Malaysian receipts are printed\n'
                '    if printed is not None:\n'
                '        parsed_date = printed                                # trust the printed text over a mis-converted ISO date\n'
                '    merchant = (data.get("merchant") or "").strip() or None\n'
                '    out = finalize({"merchant": merchant, "date": parsed_date, "amount": amount})\n'
                '    out["date_text"] = date_text\n'
                '    return out\n')


edit("src/preprocessor.py", f_pre)


# ============================================================ pages/2_Receipts.py
def f_receipts(s):
    if "def _spread" in s:
        return s
    s = swap(s, "def item_editor(key, items, total, default_label):", '''def _spread(groups, diff):
    """Spread `diff` (RM, may be negative) over the category totals in proportion to their size, in whole sen."""
    total = sum(groups.values())
    cents = round(diff * 100)
    alloc = {k: round(cents * v / total) for k, v in groups.items()}
    alloc[max(groups, key=groups.get)] += cents - sum(alloc.values())
    return {k: round(groups[k] + alloc[k] / 100, 2) for k in groups}


def item_editor(key, items, total, default_label):''')
    a = s.index("    diff = round(float(total) - round(sum(groups.values()), 2), 2)\n    ok = True\n")
    b = s.index("    if ok:\n        st.markdown(f\"**{t('Transactions that will be saved')}**\")")
    new = '''    items_sum = round(sum(groups.values()), 2)
    diff = round(float(total) - items_sum, 2)          # < 0: discount / voucher,  > 0: delivery, service charge, tax
    ok = True
    if abs(diff) > 0.005:
        if total > 0 and abs(diff) <= 0.7 * max(items_sum, float(total)):
            groups = _spread(groups, diff)
            ok = all(v > 0 for v in groups.values())
            if abs(diff) <= 0.10:
                st.caption(t("Rounding of {d} is spread across the categories.", d=ui.money(abs(diff))))
            elif diff < 0:
                st.info(t("Discount or voucher of {d} detected: the items add up to {s} but you paid {tot}. "
                          "It is spread across the categories in proportion to their amounts.",
                          d=ui.money(abs(diff)), s=ui.money(items_sum), tot=ui.money(total)))
            else:
                st.info(t("Extra charges of {d} (delivery, service charge, tax) detected: the items add up to {s} but you paid {tot}. "
                          "They are spread across the categories in proportion to their amounts.",
                          d=ui.money(diff), s=ui.money(items_sum), tot=ui.money(total)))
        else:
            ok = False
            st.warning(t("The items add up to {s} but the receipt total is {tot}. Fix the items or the total.",
                         s=ui.money(items_sum), tot=ui.money(total)))
'''
    s = s[:a] + new + s[b:]
    s = swap(s, '        tx_date = c1.date_input(t("Date"), value=res["date"], key=f"cf_d_{k}")\n',
             '        tx_date = c1.date_input(t("Date"), value=res["date"], key=f"cf_d_{k}")\n'
             '        if res.get("date_text"):\n'
             '            c1.caption(t("Printed on the receipt: {d}", d=res["date_text"]))\n'
             '        if (date.today() - tx_date).days < 0 or (date.today() - tx_date).days > 400:\n'
             '            c1.warning(t("This date looks unusual ({d}). Please check it.", d=str(tx_date)))\n')
    s = swap(s, "{r['upload_date'][:10]}", "{ui.local_time(r['upload_date'], False)}")
    return s


edit("pages/2_Receipts.py", f_receipts)


# ============================================================ pages/3_Transactions.py
def f_tx(s):
    if "before discounts and fees" in s:
        return s
    return swap(s, '                                   t("Category"): [ui.cat_label(i["category_name"]) for i in its]}),\n'
                   '                     width="stretch", hide_index=True)\n',
                '                                   t("Category"): [ui.cat_label(i["category_name"]) for i in its]}),\n'
                '                     width="stretch", hide_index=True)\n'
                '        if abs(sum(i["amount"] for i in its) - float(r["amount"])) > 0.005:\n'
                '            st.caption(t("Item prices are shown before discounts and fees. The transaction amount is what you paid."))\n')


edit("pages/3_Transactions.py", f_tx)


# ============================================================ utils/i18n.py
def f_i18n(s):
    if "Printed on the receipt" in s:
        return s
    return s + """

MS.update({
    "Rounding of {d} is spread across the categories.": "Pembundaran {d} diagihkan antara kategori.",
    "Discount or voucher of {d} detected: the items add up to {s} but you paid {tot}. It is spread across the categories in proportion to their amounts.":
        "Diskaun atau baucar {d} dikesan: jumlah barang {s} tetapi anda membayar {tot}. Ia diagihkan antara kategori mengikut nisbah jumlah.",
    "Extra charges of {d} (delivery, service charge, tax) detected: the items add up to {s} but you paid {tot}. They are spread across the categories in proportion to their amounts.":
        "Caj tambahan {d} (penghantaran, caj perkhidmatan, cukai) dikesan: jumlah barang {s} tetapi anda membayar {tot}. Ia diagihkan antara kategori mengikut nisbah jumlah.",
    "Printed on the receipt: {d}": "Tertera pada resit: {d}",
    "This date looks unusual ({d}). Please check it.": "Tarikh ini nampak luar biasa ({d}). Sila semak.",
    "Item prices are shown before discounts and fees. The transaction amount is what you paid.":
        "Harga barang dipaparkan sebelum diskaun dan caj. Jumlah transaksi ialah yang anda bayar.",
})
"""


edit("utils/i18n.py", f_i18n)
print("Done. Restart Streamlit.")