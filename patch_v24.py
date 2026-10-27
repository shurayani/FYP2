"""One-time patch #24: Recurring bills and Price check move INTO the Transactions page as tabs.
  Transactions page:  History (as before) | Recurring bills | Price check
  * recurring bills create transactions, and price check reads the items stored with transactions, so both
    belong to Transaction Management instead of being two extra modules
  * the separate 'Price Check' and 'Recurring Bills' pages are removed from the menu
  * bill reminders still appear on the Dashboard
Nothing in the database or sync changes.   Run once from the project folder:   python patch_v24.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


# ============================================================ utils/tx_tabs.py (the two former pages as functions)
(ROOT / "utils" / "tx_tabs.py").write_text(r'''"""Extra tabs on the Transactions page (patch #24): recurring bills and price check.
They used to be separate pages (patch #23); they belong to transaction management:
recurring bills create transactions, and price check reads the items stored with transactions."""
import difflib
import re
from datetime import date

import pandas as pd
import streamlit as st

from src import db_manager as db, recurring
from utils import ui
from utils.i18n import t


def render_recurring(uid):
    """Recurring bills: reminders (Add / Change amount / Skip), add, list, pause/resume, edit, delete, suggestions."""
    st.caption(t("Get a reminder for bills you pay every month, like Netflix, a phone plan or rent. Nothing is added automatically: each month you add, change or skip the payment, and you can pause a bill at any time."))

    ui.bill_reminders(uid, "rb")

    cats = ui.category_map(uid)
    labels = list(cats.keys())
    id_to_label = {v: k for k, v in cats.items()}
    bills = db.get_bills(uid)

    # ------------------------------------------------------------------ add
    with st.expander(t("Add a recurring bill"), expanded=not bills):
        n = st.session_state.setdefault("bill_n", 0)
        with st.form("add_bill", clear_on_submit=True):
            name = st.text_input(t("Name"), placeholder="Netflix")
            c1, c2, c3 = st.columns(3)
            with c1:
                amt = ui.money_input(t("Amount (RM)"), value=0.0, key=f"bill_amt_{n}")
            cat = c2.selectbox(t("Category"), labels, key="bill_cat")
            day = c3.number_input(t("Day of the month"), min_value=1, max_value=31, value=date.today().day, step=1)
            ok = st.form_submit_button(t("Save bill"), type="primary")
        if ok:
            if not name.strip() or amt <= 0:
                st.error(t("A name and a positive amount are required."))
            else:
                db.add_bill(uid, name, amt, cats[cat], int(day))
                st.session_state["bill_n"] = n + 1
                st.rerun()

    # ------------------------------------------------------------------ list
    if bills:
        st.subheader(t("Your recurring bills"), anchor=False)
    for b in bills:
        with st.container(border=True, key=f"bill_row_{b['id']}"):
            c1, c2, c3 = st.columns([4, 1, 1], vertical_alignment="center")
            state = t("Active") if b["status"] == "active" else t("Paused")
            c1.markdown(f"**{b['name']}** · {ui.money(b['amount'])}  \n"
                        f"{ui.cat_label(b['category_name'])} · {t('every month on day {d}', d=b['day_of_month'])} · {state}")
            if b["status"] == "active":
                if c2.button(t("Pause"), key=f"pause_{b['id']}"):
                    db.update_bill(b["id"], uid, status="paused")
                    st.rerun()
            elif c2.button(t("Resume"), key=f"resume_{b['id']}"):
                db.update_bill(b["id"], uid, status="active")
                st.rerun()
            with c3.popover(t("Edit")):
                with st.form(f"edit_bill_{b['id']}"):
                    e_name = st.text_input(t("Name"), value=b["name"])
                    e_amt = ui.money_input(t("Amount (RM)"), value=float(b["amount"]), key=f"e_amt_{b['id']}")
                    cur = id_to_label.get(b["category_id"], labels[0])
                    e_cat = st.selectbox(t("Category"), labels, index=labels.index(cur))
                    e_day = st.number_input(t("Day of the month"), 1, 31, int(b["day_of_month"]))
                    save = st.form_submit_button(t("Save changes"), type="primary")
                    delete = st.form_submit_button(t("Delete bill"))
                if save and e_name.strip() and e_amt > 0:
                    db.update_bill(b["id"], uid, name=e_name.strip(), amount=e_amt, category_id=cats[e_cat],
                                   day_of_month=int(e_day))
                    st.rerun()
                if delete:
                    db.delete_bill(b["id"], uid)
                    st.rerun()

    # ------------------------------------------------------------------ suggestions from the history
    sug = recurring.suggestions(uid)
    if sug:
        st.subheader(t("Found in your history"), anchor=False)
        st.caption(t("You paid these with a similar amount in at least 3 of the last 4 months."))
        for i, s in enumerate(sug):
            c1, c2 = st.columns([4, 1], vertical_alignment="center")
            c1.markdown(f"**{s['name']}** · {ui.money(s['amount'])} · {ui.cat_label(s['category_name'])} · "
                        f"{t('every month on day {d}', d=s['day_of_month'])}")
            if c2.button(t("Add as recurring"), key=f"sug_{i}"):
                db.add_bill(uid, s["name"], s["amount"], s["category_id"], s["day_of_month"])
                st.rerun()


def render_price_check(uid):
    """Price check: compare what was paid for an item at each shop (from receipt items)."""
    st.caption(t("Search for something you have bought before to see what you paid at each shop and where it was cheapest."))

    items = db.get_item_history(uid)
    if not items:
        st.info(t("No receipt items saved yet. Scan receipts that list their items, then come back here."))
        return

    query = st.text_input(t("Item"), placeholder="Milo", key="pc_query")
    if not query.strip():
        common = pd.Series([i["item_name"].strip().upper() for i in items]).value_counts().head(8)
        if len(common):
            st.caption(t("Bought most often: {items}", items=", ".join(n.title() for n in common.index)))
        return

    tokens = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1] or [query.lower().strip()]


    def _matches(name: str) -> bool:
        words = re.findall(r"[a-z0-9]+", name.lower())
        return all(any(tok in w or difflib.SequenceMatcher(None, tok, w).ratio() >= 0.8 for w in words) for tok in tokens)


    found = [i for i in items if _matches(i["item_name"])]
    if not found:
        st.info(t("Nothing on your receipts matches '{q}'. Try a shorter word, like the brand name.", q=query))
        return

    df = pd.DataFrame(found)
    df["amount"] = df["amount"].astype(float).round(2)
    df["product"] = df["item_name"].str.strip().str.upper()
    products = sorted(df["product"].unique())
    if len(products) > 1:                              # e.g. 'MILO 1KG' and 'MILO 3IN1 18S' are different products
        chosen = st.multiselect(t("Products found"), products, default=products, key="pc_products",
                                help=t("Remove products that are not the same item (another size or pack) to compare like with like."))
        df = df[df["product"].isin(chosen)]
        if df.empty:
            st.info(t("Choose at least one product."))
            return
    cheapest = df.loc[df["amount"].idxmin()]
    dearest = df.loc[df["amount"].idxmax()]

    k = st.columns(3)
    k[0].metric(t("Cheapest"), ui.money(cheapest["amount"]))
    k[1].metric(t("Most expensive"), ui.money(dearest["amount"]))
    k[2].metric(t("Times bought"), len(df))
    st.success(t("Cheapest at {shop} on {d}: {p}.", shop=cheapest["merchant"], d=cheapest["date"],
                 p=ui.money(cheapest["amount"])))

    st.subheader(t("Lowest price at each shop"), anchor=False)
    per_shop = (df.sort_values("date", ascending=False)
                  .groupby("merchant", as_index=False)
                  .agg(low=("amount", "min"), last=("date", "first"), n=("amount", "size"))
                  .sort_values("low"))
    st.dataframe(pd.DataFrame({t("Shop"): per_shop["merchant"], t("Lowest price"): per_shop["low"].map(ui.money),
                               t("Last bought"): per_shop["last"], t("Times bought"): per_shop["n"]}),
                 width="stretch", hide_index=True)

    with st.expander(t("Every purchase ({n})", n=len(df))):
        st.dataframe(pd.DataFrame({t("Item as printed"): df["item_name"], t("Shop"): df["merchant"],
                                   t("Date"): df["date"], "RM": df["amount"]}), width="stretch", hide_index=True)
    st.caption(t("Prices are the line totals printed on the receipt. If you bought more than one, the price covers all of them, and different sizes are listed separately by name."))
''', encoding="utf-8")
print("wrote utils/tx_tabs.py")


# ============================================================ views/3_Transactions.py: three tabs
def f_tx(s):
    if "tab_hist" in s:
        return s
    s = swap(s, "from utils import ui\n", "from utils import tx_tabs, ui\n")
    anchor = "id_to_label = {v: k for k, v in cats.items()}\n"
    a = s.index(anchor) + len(anchor)
    head, rest = s[:a], s[a:]
    indented = "".join(("    " + ln if ln.strip() else ln) for ln in rest.splitlines(True))
    return (head + "\ntab_hist, tab_bills, tab_price = st.tabs([t(\"History\"), t(\"Recurring bills\"), t(\"Price check\")])\n\n"
            "with tab_hist:\n" + indented.rstrip("\n") + "\n\n"
            "with tab_bills:\n    tx_tabs.render_recurring(uid)\n\n"
            "with tab_price:\n    tx_tabs.render_price_check(uid)\n")


edit("views/3_Transactions.py", f_tx)
print("3_Transactions.py ok")


# ============================================================ app.py: remove the two pages from the menu
def f_app(s):
    s = s.replace('                  st.Page("views/11_Price_Check.py", title=t("Price Check")),\n', "")
    s = s.replace('                  st.Page("views/12_Recurring_Bills.py", title=t("Recurring Bills")),\n', "")
    return s


edit("app.py", f_app)
for name in ("views/11_Price_Check.py", "views/12_Recurring_Bills.py"):
    p = ROOT / name
    if p.exists():
        p.unlink()
        print("removed", name)


def f_i18n(s):
    if '"Recurring bills": "Bil berulang"' in s:
        return s
    return s + """

MS.update({"Recurring bills": "Bil berulang", "Price check": "Semak harga"})
"""


edit("utils/i18n.py", f_i18n)
print("Done. Commit + push, then Reboot app (and restart Streamlit on the laptop).")