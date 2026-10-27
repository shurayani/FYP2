"""One-time patch #23: four new features.
  1. CATEGORY SUGGESTIONS IN REAL USE: when IPECS suggests a category (Auto / OCR), the suggestion is stored;
     the Admin dashboard shows how often users kept it and the most common corrections - real-world accuracy
     of the classifier during UAT (beside the F1-score on the dataset)
  2. MONTHLY REPORT AS PDF: 'Download PDF' on every saved report (Reports page)
  3. PRICE CHECK page: search an item (e.g. Milo) and compare what you paid at each shop, cheapest first
  4. RECURRING BILLS page + reminders on the Dashboard: Netflix, phone plan, rent... are NOT added automatically;
     each month: Add / Change amount (this month only, or from now on) / Skip; bills can be paused and resumed;
     IPECS also suggests bills it finds in your history

SUPABASE: run supabase_patch_v23.sql (created by this patch) once in the Supabase SQL editor.
          Until you do, IPECS keeps syncing everything else normally; recurring bills and the stored category
          suggestions simply stay on the device and are sent after the SQL has been run (and Reboot / restart).
LAPTOP:   pip install reportlab      (for the PDF; Streamlit Cloud installs it from requirements.txt)
Run once from the project folder:   python patch_v23.py      then commit + push + Reboot app."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


def write_new(path, text):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    print("wrote", path)


# ============================================================ new files
write_new("src/report_pdf.py", r'''"""Monthly spending report as a PDF (patch #23). Uses reportlab; the data comes from analytics.build_report()."""
from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Drawing, Rect, String

NAVY = colors.HexColor("#16253D")
TEAL = colors.HexColor("#0F7B6C")
MUTED = colors.HexColor("#5B6B7F")
LINE = colors.HexColor("#D3DCDA")
MIST = colors.HexColor("#EDF1F0")
RED = colors.HexColor("#C2412D")
CHART = ["#0F7B6C", "#2F6DB5", "#D9861C", "#6B46A3", "#C2412D", "#4E9A3A", "#8A94A6", "#16253D"]


def _txt(s) -> str:
    """Helvetica only covers Latin-1: replace anything else, and escape for Paragraph markup."""
    s = str(s if s is not None else "")
    s = s.encode("latin-1", "replace").decode("latin-1")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _rm(x) -> str:
    try:
        return f"RM {float(x):,.2f}"
    except (TypeError, ValueError):
        return "-"


def _bars(cats, cat_label, width):
    """Horizontal bars: one per category, longest = highest spending."""
    rows = [c for c in cats if (c.get("total") or 0) > 0][:8]
    if not rows:
        return None
    bar_h, gap, label_w, value_w = 13, 7, 46 * mm, 26 * mm
    height = len(rows) * (bar_h + gap)
    d = Drawing(width, height)
    top = max(c["total"] for c in rows)
    track = width - label_w - value_w
    for i, c in enumerate(rows):
        y = height - (i + 1) * (bar_h + gap) + gap / 2
        d.add(String(0, y + 3, _txt(cat_label(c["category"]))[:28], fontName="Helvetica", fontSize=8.5, fillColor=NAVY))
        d.add(Rect(label_w, y, track, bar_h, fillColor=MIST, strokeColor=None))
        d.add(Rect(label_w, y, max(2, track * c["total"] / top), bar_h,
                   fillColor=colors.HexColor(CHART[i % len(CHART)]), strokeColor=None))
        d.add(String(width, y + 3, _rm(c["total"]), fontName="Helvetica-Bold", fontSize=8.5, fillColor=NAVY,
                     textAnchor="end"))
    return d


def build_pdf(data: dict, username: str, t, cat_label, month_text: str) -> bytes:
    """data = analytics.build_report(...); t = translation function; cat_label = category display name."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=16 * mm, title=f"IPECS {t('Monthly spending report')} {month_text}",
                            author="IPECS")
    width = A4[0] - 36 * mm
    st_h = ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=12.5, textColor=NAVY, spaceBefore=12, spaceAfter=6)
    st_p = ParagraphStyle("p", fontName="Helvetica", fontSize=9.5, textColor=NAVY, leading=13.5)
    st_small = ParagraphStyle("s", parent=st_p, fontSize=8, textColor=MUTED, leading=11)
    st_cell = ParagraphStyle("c", parent=st_p, fontSize=9, leading=11)
    story = []

    # ---- header band
    head = Table([[Paragraph("<font color='#FFFFFF' size='20'><b>IPECS</b></font>", st_p),
                   Paragraph(f"<font color='#FFFFFF' size='12'><b>{_txt(t('Monthly spending report'))}</b></font><br/>"
                             f"<font color='#C9D5DF'>{_txt(month_text)} &middot; {_txt(username)}</font>",
                             ParagraphStyle("r", parent=st_p, alignment=2, leading=16))]],
                 colWidths=[width * 0.4, width * 0.6], rowHeights=[22 * mm])
    head.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 6 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 6 * mm)]))
    story += [head, Spacer(1, 6 * mm)]

    # ---- summary: total + three figures
    change = data.get("change_pct")
    change_txt = "-" if change is None else (f"+{change:.1f}%" if change > 0 else f"{change:.1f}%")
    top = cat_label(data["top_category"]) if data.get("top_category") else "-"
    label = ParagraphStyle("l", parent=st_small)
    big = ParagraphStyle("b", parent=st_p, fontName="Helvetica-Bold", fontSize=22, textColor=TEAL, leading=26)
    val = ParagraphStyle("v", parent=st_p, fontName="Helvetica-Bold", fontSize=12, leading=15)
    summary = Table([[Paragraph(_txt(t("Total spent")), label), Paragraph(_txt(t("Transactions")), label),
                      Paragraph(_txt(t("Average per day")), label), Paragraph(_txt(t("vs previous month")), label)],
                     [Paragraph(_rm(data["total"]), big), Paragraph(str(data.get("transaction_count", 0)), val),
                      Paragraph(_rm(data.get("avg_daily")), val), Paragraph(change_txt, val)]],
                    colWidths=[width * 0.34, width * 0.22, width * 0.22, width * 0.22])
    summary.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, LINE), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                                 ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
                                 ("LEFTPADDING", (0, 0), (-1, -1), 4 * mm)]))
    story += [summary, Spacer(1, 2 * mm),
              Paragraph(_txt(t("Highest category")) + f": <b>{_txt(top)}</b>", st_small)]

    # ---- categories
    cats = data.get("categories") or []
    story.append(Paragraph(_txt(t("Spending by category")), st_h))
    if not cats:
        story.append(Paragraph(_txt(t("No spending recorded this month.")), st_p))
    else:
        bars = _bars(cats, cat_label, width)
        if bars:
            story += [bars, Spacer(1, 4 * mm)]
        rows = [[_txt(t("Category")), _txt(t("Spent")), _txt(t("Share")), _txt(t("Budget")), _txt(t("Variance"))]]
        over_rows = []
        for i, c in enumerate(cats, start=1):
            var = c.get("variance")
            rows.append([Paragraph(_txt(cat_label(c["category"])), st_cell), _rm(c["total"]), f"{c.get('share', 0):.1f}%",
                         _rm(c["budget"]) if c.get("budget") is not None else "-",
                         _rm(var) if var is not None else "-"])
            if var is not None and var < 0:
                over_rows.append(i)
        tbl = Table(rows, colWidths=[width * 0.36, width * 0.17, width * 0.13, width * 0.17, width * 0.17],
                    repeatRows=1)
        style = [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                 ("FONT", (0, 1), (-1, -1), "Helvetica", 9), ("TEXTCOLOR", (0, 1), (-1, -1), NAVY),
                 ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("LINEBELOW", (0, 0), (-1, 0), 0.8, NAVY),
                 ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                 ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
        for r in over_rows:
            style.append(("TEXTCOLOR", (4, r), (4, r), RED))
        tbl.setStyle(TableStyle(style))
        story.append(tbl)
        if over_rows:
            story.append(Spacer(1, 1.5 * mm))
            story.append(Paragraph(_txt(t("A negative variance means the category went over its budget.")), st_small))

    # ---- top merchants
    tm = data.get("top_merchants") or []
    if tm:
        story.append(Paragraph(_txt(t("Top merchants")), st_h))
        rows = [[_txt(t("Merchant")), _txt(t("Visits")), _txt(t("Spent"))]] + \
               [[Paragraph(_txt(m["merchant"]), st_cell), str(m["visits"]), _rm(m["total"])] for m in tm]
        tbl = Table(rows, colWidths=[width * 0.6, width * 0.17, width * 0.23])
        tbl.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                                 ("FONT", (0, 1), (-1, -1), "Helvetica", 9), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                                 ("LINEBELOW", (0, 0), (-1, 0), 0.8, NAVY), ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
                                 ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        story.append(tbl)

    # ---- notes
    notes = data.get("trends") or []
    if notes:
        story.append(Paragraph(_txt(t("Notes")), st_h))
        for n in notes:
            story.append(Paragraph("&bull; " + _txt(t(n)), st_p))

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, _txt(t("Generated by IPECS on {d}", d=datetime.now().strftime("%d %b %Y, %I:%M %p"))))
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"{doc_.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
''')
write_new("src/recurring.py", r'''"""Recurring bills (patch #23): REMINDERS, never automatic transactions.

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
''')
write_new("views/11_Price_Check.py", r'''"""Price Check (patch #23): compare what you paid for an item at different shops, using the items read from
your receipts. Matching is forgiving: every word you type must appear in the item name (small spelling
differences are allowed), so 'milo' also finds 'NESTLE MILO ACTIV-GO 1KG'."""
import difflib
import re

import pandas as pd
import streamlit as st

from src import db_manager as db
from utils import ui
from utils.i18n import t

user = ui.require_login()
uid = user["id"]
st.title(t("Price Check"))
st.caption(t("Search for something you have bought before to see what you paid at each shop and where it was cheapest."))

items = db.get_item_history(uid)
if not items:
    st.info(t("No receipt items saved yet. Scan receipts that list their items, then come back here."))
    st.stop()

query = st.text_input(t("Item"), placeholder="Milo", key="pc_query")
if not query.strip():
    common = pd.Series([i["item_name"].strip().upper() for i in items]).value_counts().head(8)
    if len(common):
        st.caption(t("Bought most often: {items}", items=", ".join(n.title() for n in common.index)))
    st.stop()

tokens = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1] or [query.lower().strip()]


def _matches(name: str) -> bool:
    words = re.findall(r"[a-z0-9]+", name.lower())
    return all(any(tok in w or difflib.SequenceMatcher(None, tok, w).ratio() >= 0.8 for w in words) for tok in tokens)


found = [i for i in items if _matches(i["item_name"])]
if not found:
    st.info(t("Nothing on your receipts matches '{q}'. Try a shorter word, like the brand name.", q=query))
    st.stop()

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
        st.stop()
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
''')
write_new("views/12_Recurring_Bills.py", r'''"""Recurring Bills (patch #23): reminders for bills paid every month. Nothing is added automatically -
each month the user adds, changes or skips the payment, and can pause a bill and resume it later."""
from datetime import date

import streamlit as st

from src import db_manager as db, recurring
from utils import ui
from utils.i18n import t

user = ui.require_login()
uid = user["id"]
st.title(t("Recurring Bills"))
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
''')
write_new("supabase_patch_v23.sql", """-- Patch #23: run ONCE in the Supabase SQL editor.
-- 1. the category IPECS suggested for a transaction (for the real-use accuracy on the Admin dashboard)
alter table transactions add column if not exists predicted_category_id text;
-- 2. recurring bills (reminders)
create table if not exists recurring_bills (
  id text primary key, user_id text not null references users(id), name text not null,
  amount double precision not null, category_id text not null references categories(id),
  day_of_month integer not null, status text not null default 'active', last_handled_month text,
  created_at text not null, updated_at text not null, is_deleted integer not null default 0);
alter table recurring_bills enable row level security;
""")


# ============================================================ src/db_manager.py
def f_db(s):
    if "def get_bills" in s:
        return s
    s = swap(s, '"budgets", "reports", "anomaly_alerts", "forecasts"]',
             '"budgets", "recurring_bills", "reports", "anomaly_alerts", "forecasts"]')
    # database changes for existing and new databases (run at every start, only act when needed)
    s = swap(s, '''def _create_schema(c, hash_password=None):
    """Tables + seven system categories + admin account (all idempotent)."""
    c.executescript(SCHEMA)
''', '''def _create_schema(c, hash_password=None):
    """Tables + seven system categories + admin account (all idempotent)."""
    c.executescript(SCHEMA)
    _migrate_v23(c)
''')
    s = swap(s, "def _ensure_schema(c):", '''def _migrate_v23(c):
    """Patch #23: suggested category on transactions + the recurring_bills table."""
    cols = [r[1] for r in c.execute("PRAGMA table_info(transactions)").fetchall()]
    if "predicted_category_id" not in cols:
        c.execute("ALTER TABLE transactions ADD COLUMN predicted_category_id TEXT")
    c.executescript("""
CREATE TABLE IF NOT EXISTS recurring_bills (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    amount REAL NOT NULL,
    category_id TEXT NOT NULL REFERENCES categories(id),
    day_of_month INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    last_handled_month TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_bills_user ON recurring_bills(user_id);
""")


def _ensure_schema(c):''')
    s = swap(s, "def add_transaction(user_id, merchant, date, amount, category_id, is_manual=True, receipt_id=None):",
             "def add_transaction(user_id, merchant, date, amount, category_id, is_manual=True, receipt_id=None,\n"
             "                    predicted_category_id=None):")
    s = swap(s, "is_anomaly=0, created_at=ts, updated_at=ts, is_deleted=0), user_id)\n    return tid",
             "is_anomaly=0, created_at=ts, updated_at=ts, is_deleted=0,\n"
             "                                        predicted_category_id=predicted_category_id), user_id)\n    return tid")
    # a remote row without a column (e.g. before supabase_patch_v23.sql was run) must not wipe the local value
    s = swap(s, '''        cols = [r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall()]
        data = {k: row.get(k) for k in cols}''', '''        cols = [r["name"] for r in c.execute(f"PRAGMA table_info({table})").fetchall() if r["name"] in row]
        data = {k: row.get(k) for k in cols}''')
    return s + """

# --------------------------------------------------------------------------- PATCH #23
def classifier_accuracy():
    \"\"\"How often users kept the category IPECS suggested (all users).\"\"\"
    with get_conn() as c:
        n, kept = c.execute("SELECT COUNT(*), COALESCE(SUM(category_id = predicted_category_id), 0) FROM transactions"
                            " WHERE is_deleted=0 AND predicted_category_id IS NOT NULL").fetchone()
        top = c.execute(\"\"\"
            SELECT p.category_name, a.category_name, COUNT(*) FROM transactions t
            JOIN categories p ON p.id=t.predicted_category_id JOIN categories a ON a.id=t.category_id
            WHERE t.is_deleted=0 AND t.predicted_category_id IS NOT NULL AND t.category_id<>t.predicted_category_id
            GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 5\"\"\").fetchall()
    return {"total": n or 0, "kept": kept or 0,
            "corrections": [{"suggested": a, "chosen": b, "times": k} for a, b, k in top]}


def get_item_history(user_id):
    \"\"\"Every receipt item of the user with the shop and date (Price Check).\"\"\"
    with get_conn() as c:
        return _rows(c.execute(\"\"\"
            SELECT i.item_name, i.amount, t.merchant, t.date FROM transaction_items i
            JOIN transactions t ON t.id=i.transaction_id
            WHERE i.user_id=? AND i.is_deleted=0 AND t.is_deleted=0 ORDER BY t.date DESC\"\"\", (user_id,)))


def add_bill(user_id, name, amount, category_id, day_of_month):
    bid, ts = new_id(), now()
    with get_conn() as c:
        _insert(c, "recurring_bills", dict(id=bid, user_id=user_id, name=name.strip()[:80], amount=float(amount),
                                           category_id=category_id, day_of_month=int(day_of_month), status="active",
                                           last_handled_month=None, created_at=ts, updated_at=ts, is_deleted=0),
                user_id)
    return bid


def get_bills(user_id):
    with get_conn() as c:
        return _rows(c.execute("SELECT b.*, c.category_name FROM recurring_bills b JOIN categories c ON c.id=b.category_id"
                               " WHERE b.is_deleted=0 AND b.user_id=? ORDER BY b.day_of_month, b.name", (user_id,)))


def update_bill(bill_id, user_id, **fields):
    allowed = {k: v for k, v in fields.items()
               if k in ("name", "amount", "category_id", "day_of_month", "status", "last_handled_month")}
    with get_conn() as c:
        _update(c, "recurring_bills", bill_id, allowed, user_id)


def delete_bill(bill_id, user_id):
    with get_conn() as c:
        _update(c, "recurring_bills", bill_id, {"is_deleted": 1}, user_id, "delete")
"""


edit("src/db_manager.py", f_db)
print("db_manager.py ok")


# ============================================================ src/sync_manager.py: new Supabase objects are optional
def f_sync(s):
    if "def remote_supports" in s:
        return s
    s = swap(s, "def push_pending(user_id, result):", '''_supports = {}


def remote_supports(table, column="id") -> bool:
    """Does Supabase have this table/column yet? (supabase_patch_v23.sql may not have been run.)
    A 'yes' is remembered; a 'no' is checked again after 5 minutes."""
    import time
    key = (table, column)
    hit = _supports.get(key)
    if hit is True or (hit is not None and time.time() - hit < 300):
        return hit is True
    try:
        get_client().table(table).select(column).limit(1).execute()
        _supports[key] = True
    except Exception:
        _supports[key] = time.time()
    return _supports[key] is True


def _remote_ready(table) -> bool:
    return table != "recurring_bills" or remote_supports("recurring_bills")


def _for_remote(table, row):
    """Leave out the new column while Supabase does not have it yet."""
    if table == "transactions" and "predicted_category_id" in row \\
            and not remote_supports("transactions", "predicted_category_id"):
        return {k: v for k, v in row.items() if k != "predicted_category_id"}
    return row


def push_pending(user_id, result):''')
    s = swap(s, '''        table, rid = entry["table_name"], entry["record_id"]
        local = db.get_row(table, rid)
''', '''        table, rid = entry["table_name"], entry["record_id"]
        if not _remote_ready(table):
            continue                                             # stays pending until the table exists remotely
        local = db.get_row(table, rid)
''')
    s = swap(s, '''            else:
                get_client().table(table).upsert(local).execute()
            db.mark_sync_entry(user_id, table, rid, "conflict",''', '''            else:
                get_client().table(table).upsert(_for_remote(table, local)).execute()
            db.mark_sync_entry(user_id, table, rid, "conflict",''')
    s = swap(s, '''        else:
            get_client().table(table).upsert(local).execute()
            db.mark_sync_entry(user_id, table, rid, "synced", remote_updated_at=local["updated_at"])''',
             '''        else:
            get_client().table(table).upsert(_for_remote(table, local)).execute()
            db.mark_sync_entry(user_id, table, rid, "synced", remote_updated_at=local["updated_at"])''')
    s = swap(s, '''    for table in db.SYNC_TABLES:
        q = get_client().table(table).select("*")''', '''    for table in db.SYNC_TABLES:
        if not _remote_ready(table):
            continue
        q = get_client().table(table).select("*")''')
    return s


edit("src/sync_manager.py", f_sync)


def f_cloud(s):
    if "_remote_ready" in s:
        return s
    return swap(s, '''        for table in db.SYNC_TABLES:
            for r in _all_rows(table):''', '''        for table in db.SYNC_TABLES:
            if not sync_manager._remote_ready(table):          # e.g. recurring_bills before the SQL was run
                continue
            for r in _all_rows(table):''')


edit("src/cloud_mode.py", f_cloud)
print("sync ok")


# ============================================================ store the suggested category when a transaction is saved
def f_receipts(s):
    if "predicted_category_id" in s:
        return s
    s = swap(s, '''                        db.add_transaction(uid, merchant, tx_date, amt, cats[label], is_manual=False, receipt_id=rid)
''', '''                        db.add_transaction(uid, merchant, tx_date, amt, cats[label], is_manual=False, receipt_id=rid,
                                           predicted_category_id=(cats[labels[_category_index(res["category_id"])]]
                                                                  if rows is None else None))
''')
    return swap(s, '''                db.add_transaction(uid, merchant, tx_date, amount, cid, is_manual=True)
''', '''                db.add_transaction(uid, merchant, tx_date, amount, cid, is_manual=True,
                                   predicted_category_id=cid if cat_choice == auto else None)
''')


edit("views/2_Receipts.py", f_receipts)


def f_tx(s):
    if "predicted_category_id" in s:
        return s
    return swap(s, "            db.add_transaction(uid, m, d, a, cid, is_manual=True)\n",
                "            db.add_transaction(uid, m, d, a, cid, is_manual=True,\n"
                "                               predicted_category_id=cid if c == auto else None)\n")


edit("views/3_Transactions.py", f_tx)
print("suggestions stored ok")


# ============================================================ app.py: navigation, reminders, admin accuracy
def f_app(s):
    if "11_Price_Check" in s:
        return s
    s = swap(s, '''                  st.Page("views/3_Transactions.py", title=t("Transactions")),
''', '''                  st.Page("views/3_Transactions.py", title=t("Transactions")),
                  st.Page("views/11_Price_Check.py", title=t("Price Check")),
''')
    s = swap(s, '''                  st.Page("views/5_Budget_Goals.py", title=t("Budget Goals")),
''', '''                  st.Page("views/5_Budget_Goals.py", title=t("Budget Goals")),
                  st.Page("views/12_Recurring_Bills.py", title=t("Recurring Bills")),
''')
    s = swap(s, '''    ui.budget_banner(uid)

    slip_col, glance_col''', '''    ui.budget_banner(uid)
    ui.bill_reminders(uid, "dash")

    slip_col, glance_col''')
    s = swap(s, '''            k[3].metric(t("Active anomaly alerts"), db.count_active_alerts_all())
''', '''            k[3].metric(t("Active anomaly alerts"), db.count_active_alerts_all())

        acc = db.classifier_accuracy()
        st.subheader(t("Category suggestions in real use"), anchor=False)
        if not acc["total"]:
            st.caption(t("No data yet. This fills in as users save transactions with the category IPECS suggested."))
        else:
            a1, a2 = st.columns([1, 2], gap="large")
            a1.metric(t("Suggestions kept by users"), f"{acc['kept'] / acc['total'] * 100:.0f}%")
            a1.caption(t("{k} of {n} suggested categories were kept.", k=acc["kept"], n=acc["total"]))
            with a2:
                if acc["corrections"]:
                    st.caption(t("Most common corrections"))
                    st.dataframe(pd.DataFrame({
                        t("Suggested"): [ui.cat_label(c_["suggested"]) for c_ in acc["corrections"]],
                        t("Changed to"): [ui.cat_label(c_["chosen"]) for c_ in acc["corrections"]],
                        t("Times"): [c_["times"] for c_ in acc["corrections"]]}), width="stretch", hide_index=True)
                else:
                    st.caption(t("No suggestion has been corrected so far."))
''')
    return s


edit("app.py", f_app)
print("app.py ok")


# ============================================================ utils/ui.py: bill reminders
def f_ui(s):
    if "def bill_reminders" in s:
        return s
    return s + r'''


def bill_reminders(user_id, key_prefix="dash"):
    """Recurring bills that are due: Add / Change amount / Skip (patch #23). Nothing happens automatically."""
    from src import analytics, recurring
    due = recurring.due_bills(user_id)
    if not due:
        return
    st.subheader(t("Bills due"), anchor=False)
    for b in due:
        when = (t("overdue since {d}", d=f"{b['due'].day} {b['due']:%b}") if b["overdue"]
                else t("due {d}", d=f"{b['due'].day} {b['due']:%b}"))
        with st.container(border=True, key=f"{key_prefix}_bill_{b['id']}"):
            c1, c2, c3, c4 = st.columns([3, 1, 1.4, 1], vertical_alignment="center")
            c1.markdown(f"**{b['name']}** · {money(b['amount'])}  \n{cat_label(b['category_name'])} · {when}")
            if c2.button(t("Add"), key=f"{key_prefix}_add_{b['id']}", type="primary"):
                recurring.confirm(b, user_id)
                analytics.detect_anomalies(user_id)
                st.rerun()
            with c3.popover(t("Change amount")):
                new_amt = money_input(t("This month's amount"), value=float(b["amount"]),
                                      key=f"{key_prefix}_amt_{b['id']}")
                keep = st.checkbox(t("Use this amount from now on"), key=f"{key_prefix}_keep_{b['id']}")
                if st.button(t("Add with this amount"), key=f"{key_prefix}_addamt_{b['id']}") and new_amt > 0:
                    recurring.confirm(b, user_id, amount=new_amt, keep_amount=keep)
                    analytics.detect_anomalies(user_id)
                    st.rerun()
            if c4.button(t("Skip"), key=f"{key_prefix}_skip_{b['id']}"):
                recurring.skip(b, user_id)
                st.rerun()
'''


edit("utils/ui.py", f_ui)
print("ui.py ok")


# ============================================================ Reports page: Download PDF
def f_reports(s):
    if "report_pdf" in s:
        return s
    return swap(s, '''        b1, b2 = st.columns(2)
        if b1.button(t("Regenerate"), key=f"rg_{r['id']}"):''', '''        try:
            from src import report_pdf
            pdf = report_pdf.build_pdf(data, user["username"], t, ui.cat_label, ui.month_label(r["report_month"]))
            st.download_button(t("Download PDF"), pdf, file_name=f"IPECS_report_{r['report_month']}.pdf",
                               mime="application/pdf", key=f"pdf_{r['id']}", icon=":material/picture_as_pdf:")
        except ImportError:
            st.caption(t("PDF download needs the reportlab package: pip install reportlab"))
        b1, b2 = st.columns(2)
        if b1.button(t("Regenerate"), key=f"rg_{r['id']}"):''')


edit("views/6_Reports.py", f_reports)


def f_req(s):
    return s if "reportlab" in s else s.rstrip("\n") + "\nreportlab>=4.0\n"


edit("requirements.txt", f_req)
print("reports + requirements ok")


# ============================================================ utils/i18n.py
def f_i18n(s):
    if "Recurring Bills" in s:
        return s
    return s + """

MS.update({
    # navigation
    "Price Check": "Semak Harga", "Recurring Bills": "Bil Berulang",
    # admin: suggestions in real use
    "Category suggestions in real use": "Cadangan kategori dalam penggunaan sebenar",
    "No data yet. This fills in as users save transactions with the category IPECS suggested.":
        "Belum ada data. Ia akan terisi apabila pengguna menyimpan transaksi dengan kategori yang dicadangkan IPECS.",
    "Suggestions kept by users": "Cadangan dikekalkan pengguna",
    "{k} of {n} suggested categories were kept.": "{k} daripada {n} kategori yang dicadangkan dikekalkan.",
    "Most common corrections": "Pembetulan paling kerap", "Suggested": "Dicadangkan", "Changed to": "Ditukar kepada",
    "Times": "Kali", "No suggestion has been corrected so far.": "Belum ada cadangan yang dibetulkan.",
    # PDF
    "Download PDF": "Muat turun PDF", "Monthly spending report": "Laporan perbelanjaan bulanan",
    "Total spent": "Jumlah dibelanjakan", "Average per day": "Purata sehari", "vs previous month": "berbanding bulan lepas",
    "Spending by category": "Perbelanjaan mengikut kategori", "Share": "Bahagian", "Variance": "Varians",
    "A negative variance means the category went over its budget.":
        "Varians negatif bermaksud kategori itu melebihi belanjawan.",
    "Visits": "Lawatan", "Notes": "Nota", "Generated by IPECS on {d}": "Dijana oleh IPECS pada {d}",
    "PDF download needs the reportlab package: pip install reportlab":
        "Muat turun PDF memerlukan pakej reportlab: pip install reportlab",
    # price check
    "Search for something you have bought before to see what you paid at each shop and where it was cheapest.":
        "Cari barang yang pernah anda beli untuk melihat harga di setiap kedai dan di mana paling murah.",
    "No receipt items saved yet. Scan receipts that list their items, then come back here.":
        "Belum ada barang resit disimpan. Imbas resit yang menyenaraikan barang, kemudian kembali ke sini.",
    "Bought most often: {items}": "Paling kerap dibeli: {items}",
    "Nothing on your receipts matches '{q}'. Try a shorter word, like the brand name.":
        "Tiada barang pada resit anda sepadan dengan '{q}'. Cuba perkataan lebih pendek, seperti jenama.",
    "Cheapest": "Paling murah", "Most expensive": "Paling mahal", "Times bought": "Kali dibeli",
    "Cheapest at {shop} on {d}: {p}.": "Paling murah di {shop} pada {d}: {p}.",
    "Lowest price at each shop": "Harga terendah di setiap kedai", "Shop": "Kedai", "Lowest price": "Harga terendah",
    "Products found": "Produk ditemui",
    "Remove products that are not the same item (another size or pack) to compare like with like.":
        "Buang produk yang bukan barang sama (saiz atau pek lain) supaya perbandingan adil.",
    "Choose at least one product.": "Pilih sekurang-kurangnya satu produk.",
    "Last bought": "Terakhir dibeli", "Every purchase ({n})": "Setiap pembelian ({n})", "Item as printed": "Barang seperti dicetak",
    "Prices are the line totals printed on the receipt. If you bought more than one, the price covers all of them, and different sizes are listed separately by name.":
        "Harga ialah jumlah baris yang dicetak pada resit. Jika anda membeli lebih daripada satu, harga meliputi semuanya, dan saiz berbeza disenaraikan berasingan mengikut nama.",
    # recurring bills
    "Get a reminder for bills you pay every month, like Netflix, a phone plan or rent. Nothing is added automatically: each month you add, change or skip the payment, and you can pause a bill at any time.":
        "Dapatkan peringatan untuk bil yang anda bayar setiap bulan, seperti Netflix, pelan telefon atau sewa. Tiada apa-apa ditambah secara automatik: setiap bulan anda tambah, ubah atau langkau bayaran, dan anda boleh menjeda bil pada bila-bila masa.",
    "Add a recurring bill": "Tambah bil berulang", "Day of the month": "Hari dalam bulan", "Save bill": "Simpan bil",
    "A name and a positive amount are required.": "Nama dan jumlah positif diperlukan.",
    "Your recurring bills": "Bil berulang anda", "Paused": "Dijeda", "every month on day {d}": "setiap bulan pada hari {d}",
    "Pause": "Jeda", "Resume": "Sambung", "Edit": "Ubah", "Delete bill": "Padam bil",
    "Found in your history": "Ditemui dalam sejarah anda",
    "You paid these with a similar amount in at least 3 of the last 4 months.":
        "Anda membayar ini dengan jumlah yang hampir sama dalam sekurang-kurangnya 3 daripada 4 bulan lepas.",
    "Add as recurring": "Tambah sebagai berulang", "Bills due": "Bil perlu dibayar",
    "overdue since {d}": "tertunggak sejak {d}", "due {d}": "perlu dibayar {d}", "Skip": "Langkau",
    "Change amount": "Ubah jumlah", "This month's amount": "Jumlah bulan ini",
    "Use this amount from now on": "Guna jumlah ini mulai sekarang", "Add with this amount": "Tambah dengan jumlah ini",
})
"""


edit("utils/i18n.py", f_i18n)
print("Done. Run supabase_patch_v23.sql in Supabase, pip install reportlab, then commit + push + Reboot app.")