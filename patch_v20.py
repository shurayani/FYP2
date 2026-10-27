"""One-time patch #20: a new look for IPECS, built around receipts and the ringgit.

  * colours taken from Malaysian banknotes: ink navy (text, sidebar), RM50 teal (main colour), RM100 violet,
    RM10 red (over budget), RM20 orange (close to the limit) - also used for every chart
  * fonts: Bricolage Grotesque (headings), Figtree (text), IBM Plex Mono (the receipt slip)
  * dashboard opens with THIS MONTH'S RECEIPT: a printed-receipt slip with a torn edge listing what you spent
    per category and the total, next to budget used, alerts, transactions and next month's forecast
  * dark navy sidebar with the IPECS mark, a calmer menu and profile card
  * login page: IPECS mark, name and a one-line description, in a narrower centred column
  * section titles are real headings; amount input, install card and app icons use the same colours
Everything is styling: no data, database or sync code is changed.
Run once from the project folder:   python patch_v20.py      then commit + push + Reboot app."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

NAVY, TEAL, TEAL_LIGHT, MIST, LINE, MUTED = "#16253D", "#0F7B6C", "#3FB8A4", "#EDF1F0", "#D3DCDA", "#5B6B7F"
CHART = ["#0F7B6C", "#2F6DB5", "#D9861C", "#6B46A3", "#C2412D", "#4E9A3A", "#8A94A6"]


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:80]
    return s.replace(old, new, 1)


# ============================================================ .streamlit/config.toml (official Streamlit theme)
FONT = "Figtree:https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700&display=swap"
HEAD = "Bricolage Grotesque:https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@600;700;800&display=swap"
CODE = "IBM Plex Mono:https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&display=swap"
(ROOT / ".streamlit" / "config.toml").write_text(f'''# IPECS theme (patch #20) - colours from Malaysian banknotes
[theme]
base = "light"
primaryColor = "{TEAL}"
backgroundColor = "{MIST}"
secondaryBackgroundColor = "#FFFFFF"
textColor = "{NAVY}"
linkColor = "{TEAL}"
borderColor = "{LINE}"
showWidgetBorder = true
baseRadius = "0.6rem"
buttonRadius = "0.6rem"
font = "{FONT}"
headingFont = "{HEAD}"
codeFont = "{CODE}"
headingFontSizes = ["2.1rem", "1.45rem", "1.12rem"]
headingFontWeights = [800, 700, 700]
redColor = "#C2412D"
orangeColor = "#D9861C"
greenColor = "#2E8B57"
blueColor = "#2F6DB5"
violetColor = "#6B46A3"
dataframeHeaderBackgroundColor = "#F3F6F5"
chartCategoricalColors = {json.dumps(CHART)}

[theme.sidebar]
backgroundColor = "{NAVY}"
secondaryBackgroundColor = "#22344F"
textColor = "#E6EDF2"
borderColor = "#2C4060"
primaryColor = "{TEAL_LIGHT}"
linkColor = "{TEAL_LIGHT}"
''', encoding="utf-8")
print("wrote .streamlit/config.toml")


# ============================================================ utils/ui.py: helpers for the new pieces
def f_ui(s):
    if "def receipt_slip" in s:
        return s
    return s + r'''


# ---------------------------------------------------------------- look & feel (patch #20)
from html import escape as _esc

CHART_COLORS = ["#0F7B6C", "#2F6DB5", "#D9861C", "#6B46A3", "#C2412D", "#4E9A3A", "#8A94A6"]
try:                                                    # same banknote colours in every Plotly chart
    import plotly.express as _px
    _px.defaults.color_discrete_sequence = CHART_COLORS
except Exception:
    pass

_MONTHS_MS = ["Januari", "Februari", "Mac", "April", "Mei", "Jun", "Julai", "Ogos", "September", "Oktober",
              "November", "Disember"]


def month_label(month: str) -> str:
    """'2026-10' -> 'October 2026' (or 'Oktober 2026' in BM)."""
    try:
        y, m = month.split("-")
        m = int(m)
    except (ValueError, AttributeError):
        return str(month)
    name = _MONTHS_MS[m - 1] if st.session_state.get("lang") == "ms" else date(2000, m, 1).strftime("%B")
    return f"{name} {y}"


def mark_svg(bg="#16253D", size=48) -> str:
    """The IPECS mark: a receipt with a torn edge."""
    return (f"<svg width='{size}' height='{size}' viewBox='0 0 48 48' xmlns='http://www.w3.org/2000/svg' "
            f"aria-hidden='true'><rect width='48' height='48' rx='12' fill='{bg}'/>"
            "<path d='M15 10h18v27l-3-2.5-3 2.5-3-2.5-3 2.5-3-2.5-3 2.5z' fill='#FFFFFF'/>"
            "<path d='M19 16.5h10M19 21h7M19 25.5h10' stroke='#3FB8A4' stroke-width='2.2' "
            "stroke-linecap='round'/></svg>")


def sidebar_brand() -> str:
    return f"<div class='side-brand'>{mark_svg('#0F7B6C', 30)}<span>IPECS</span></div>"


def brand_header() -> str:
    return ("<div class='brand'>" + mark_svg() +
            "<div><div class='brand-name'>IPECS</div>"
            f"<div class='brand-tag'>{_esc(t('Intelligent Personal Expense Categorization System'))}</div></div></div>"
            f"<p class='brand-pitch'>{_esc(t('Snap a receipt and IPECS sorts your spending into categories, tracks your budgets and warns you about unusual expenses.'))}</p>")


def receipt_slip(month_text, lines, total, top_category=None) -> str:
    """This month's spending printed like a receipt. lines = [(category label, amount)]."""
    rows = "".join(f"<div class='slip-line'><span class='slip-item'>{_esc(name)}</span><span class='slip-dots'></span>"
                   f"<span class='slip-amt'>{money(amount)}</span></div>" for name, amount in lines)
    if not rows:
        rows = f"<div class='slip-empty'>{_esc(t('No spending recorded yet this month.'))}</div>"
    foot = (f"<div class='slip-foot'>{_esc(t('Most frequent category: {c}', c=top_category))}</div>"
            if top_category else "")
    return ("<div class='slip-wrap'><div class='slip'>"
            f"<div class='slip-head'><span class='slip-brand'>IPECS</span><span>{_esc(month_text)}</span></div>"
            f"<div class='slip-sub'>{_esc(t('Spending so far this month'))}</div><div class='slip-rule'></div>"
            f"{rows}<div class='slip-rule'></div>"
            f"<div class='slip-total'><span>{_esc(t('Total'))}</span><span>{money(total)}</span></div>{foot}"
            "</div></div>")


def budget_meter(pct) -> str:
    """Budget used this month as a bar: teal, orange from 75 %, red from 100 %."""
    if pct is None:
        return (f"<div class='meter'><div class='meter-top'><span>{_esc(t('Budget used this month'))}</span>"
                f"<b>—</b></div><div class='meter-note'>{_esc(t('No budget goals set for this month.'))}</div></div>")
    colour = "#C2412D" if pct >= 100 else "#D9861C" if pct >= 75 else "#0F7B6C"
    return (f"<div class='meter'><div class='meter-top'><span>{_esc(t('Budget used this month'))}</span>"
            f"<b>{pct:.0f}%</b></div><div class='meter-track'>"
            f"<div class='meter-fill' style='width:{max(0, min(100, pct)):.0f}%;background:{colour}'></div></div></div>")
'''


edit("utils/ui.py", f_ui)
print("ui.py ok")


# ============================================================ app.py
NEW_CSS = r'''BASE_CSS = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
h1 { letter-spacing: -0.02em; }
h2, h3 { letter-spacing: -0.01em; }

/* ---------- sidebar (its colours come from [theme.sidebar] in .streamlit/config.toml) */
.side-brand { display:flex; align-items:center; gap:10px; margin:0 0 1rem 2px; }
.side-brand svg { flex:none; }
.side-brand span { font-family:"Bricolage Grotesque", sans-serif; font-weight:800; font-size:1.25rem;
    color:#F4F7F6; letter-spacing:-0.01em; }
.profile-card { display:flex; align-items:center; gap:12px; padding:0.7rem 0.8rem; margin-bottom:0.25rem;
    background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.12); border-radius:12px;
    transition:background .15s ease, border-color .15s ease; }
.profile-avatar { width:38px; height:38px; border-radius:50%; background:#3FB8A4; color:#16253D; flex:none;
    display:flex; align-items:center; justify-content:center; font-weight:800; font-size:1rem;
    font-family:"Bricolage Grotesque", sans-serif; }
.profile-name { font-weight:650; line-height:1.2; color:#F4F7F6; }
.profile-role { font-size:0.78rem; color:#9FB2C4; }
.profile-role::first-letter { text-transform:uppercase; }
.st-key-profilebox { position:relative; }
.st-key-profilebox [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) { position:absolute; inset:0; z-index:5; }
.st-key-profilebox [data-testid="stPageLink-NavLink"] { opacity:0; height:100%; width:100%; }
.st-key-profilebox:hover .profile-card { background:rgba(255,255,255,0.1); border-color:rgba(63,184,164,0.6); }
.profile-card.profile-active { background:rgba(63,184,164,0.14); border-color:#3FB8A4; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] { border:0; border-radius:8px; padding:0.45rem 0.75rem;
    margin-bottom:2px; background:transparent; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p { color:#C9D5DF; font-weight:500; }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover { background:rgba(255,255,255,0.07); }
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover p { color:#FFFFFF; }
.nav-active { box-sizing:border-box; display:flex; align-items:center; min-height:38px; border-radius:8px;
    padding:0 0.75rem; margin:2px 0 6px; background:#0F7B6C; color:#FFFFFF !important; font-weight:600;
    font-size:0.875rem; box-shadow:inset 3px 0 0 #3FB8A4; }
[data-testid="stSidebar"] hr { border-color:rgba(255,255,255,0.1); margin:0.8rem 0; }

/* ---------- metrics and forms */
[data-testid="stMetric"] { background:#FFFFFF; border:1px solid #D3DCDA; border-radius:12px; padding:0.85rem 1rem; }
[data-testid="stMetricLabel"] p { font-size:0.82rem !important; color:#5B6B7F; }
[data-testid="stMetricValue"] { font-family:"Bricolage Grotesque", sans-serif; font-size:1.45rem !important;
    font-weight:700; color:#16253D; }
[data-testid="stMetricValue"] p, [data-testid="stMetricLabel"] p,
[data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"] {
    white-space:normal !important; overflow:visible !important; text-overflow:clip !important;
    overflow-wrap:anywhere; line-height:1.25; }
.st-key-glance [data-testid="stHorizontalBlock"] { display:grid !important;
    grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:0.75rem; }
.st-key-glance [data-testid="stColumn"] { width:auto !important; min-width:0 !important; flex:unset !important; }
[data-testid="stForm"] { background:#FFFFFF; border:1px solid #D3DCDA; border-radius:14px; padding:1.1rem 1.2rem; }
.stButton > button, .stDownloadButton > button, [data-testid^="stBaseButton"] { font-weight:600; }

/* ---------- dashboard quick actions */
.st-key-quick_actions [data-testid="stPageLink-NavLink"] { background:#FFFFFF; border:1px solid #D3DCDA;
    border-radius:10px; padding:0.45rem 0.9rem; }
.st-key-quick_actions [data-testid="stPageLink-NavLink"]:hover { border-color:#0F7B6C; }
.st-key-qa_scan [data-testid="stPageLink-NavLink"] { background:#0F7B6C; border-color:#0F7B6C; }
.st-key-qa_scan [data-testid="stPageLink-NavLink"]:hover { background:#0C6559; }
.st-key-qa_scan [data-testid="stPageLink-NavLink"] p, .st-key-qa_scan [data-testid="stPageLink-NavLink"] span { color:#FFFFFF !important; }

/* ---------- this month's receipt (dashboard) */
.slip-wrap { filter:drop-shadow(0 1px 0 #D3DCDA) drop-shadow(0 10px 16px rgba(22,37,61,0.08)); margin-bottom:1rem; }
.slip { --z:9px; background:#FFFFFF; padding:1.25rem 1.4rem calc(1.25rem + var(--z)); color:#16253D;
    font-family:"IBM Plex Mono", ui-monospace, monospace; font-size:0.9rem;
    -webkit-mask:conic-gradient(from -45deg at bottom, #0000, #000 1deg 89deg, #0000 90deg) 50% / calc(2 * var(--z)) 100%;
            mask:conic-gradient(from -45deg at bottom, #0000, #000 1deg 89deg, #0000 90deg) 50% / calc(2 * var(--z)) 100%; }
.slip-head { display:flex; justify-content:space-between; align-items:baseline; gap:1rem; font-weight:600; }
.slip-brand { font-family:"Bricolage Grotesque", sans-serif; font-weight:800; font-size:1.15rem; }
.slip-sub { color:#5B6B7F; font-size:0.8rem; margin-top:2px; }
.slip-rule { border-top:1.5px dashed #AEBBC0; margin:0.8rem 0; }
.slip-line { display:flex; align-items:baseline; gap:6px; padding:3px 0; }
.slip-item { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:62%; }
.slip-dots { flex:1; min-width:12px; border-bottom:1.5px dotted #C5CFD2; transform:translateY(-4px); }
.slip-amt { white-space:nowrap; font-variant-numeric:tabular-nums; }
.slip-total { display:flex; justify-content:space-between; align-items:baseline; gap:1rem; font-weight:700; }
.slip-total span:last-child { font-family:"Bricolage Grotesque", sans-serif; font-size:2.1rem; line-height:1.1;
    letter-spacing:-0.02em; color:#0F7B6C; }
.slip-foot { margin-top:0.6rem; font-size:0.8rem; color:#5B6B7F; }
.slip-empty { color:#5B6B7F; padding:0.3rem 0; }
.meter { background:#FFFFFF; border:1px solid #D3DCDA; border-radius:12px; padding:0.85rem 1rem; margin-bottom:0.75rem; }
.meter-top { display:flex; justify-content:space-between; align-items:baseline; font-size:0.82rem; color:#5B6B7F; }
.meter-top b { font-family:"Bricolage Grotesque", sans-serif; font-size:1.45rem; color:#16253D; }
.meter-track { height:10px; background:#E3E9E7; border-radius:99px; margin-top:0.5rem; overflow:hidden; }
.meter-fill { height:100%; border-radius:99px; }
.meter-note { font-size:0.82rem; color:#5B6B7F; margin-top:0.3rem; }

/* ---------- login page */
.brand { display:flex; align-items:center; gap:14px; margin:0.5rem 0 0.6rem; }
.brand svg { flex:none; }
.brand-name { font-family:"Bricolage Grotesque", sans-serif; font-weight:800; font-size:2.5rem; line-height:1;
    letter-spacing:-0.03em; color:#16253D; }
.brand-tag { color:#5B6B7F; font-size:0.9rem; margin-top:4px; }
.brand-pitch { font-size:1.02rem; line-height:1.55; color:#2A3A52; max-width:34rem; margin:0.4rem 0 1rem; }
</style>
"""
'''


def f_app(s):
    if "receipt_slip" in s:
        return s
    a = s.index('BASE_CSS = """')
    b = s.index("# Dark mode:")
    s = s[:a] + NEW_CSS + "\n" + s[b:]
    # admin keeps a plain title; users get a greeting instead
    s = swap(s, '''    st.title(f"IPECS — {t('Dashboard')}")
    if user["role"] == "admin":
''', '''    if user["role"] == "admin":
        st.title(t("Dashboard"))
''')
    a = s.index('    uid = user["id"]\n    st.subheader(t("Hello, {name}!", name=user["username"]))\n')
    end = '        st.page_link("views/2_Receipts.py", label=t("Add your first transaction"))\n'
    b = s.index(end) + len(end)
    s = s[:a] + '''    uid = user["id"]
    month = analytics.month_str(date.today())
    summary = analytics.monthly_summary(uid, month)
    total = float(summary["total"].sum()) if not summary.empty else 0.0
    all_tx = db.get_transactions(uid)
    top_cat = None
    if not summary.empty:                       # most frequent = highest number of transactions
        top_cat = ui.cat_label(summary.sort_values("count", ascending=False).iloc[0]["category_name"])
    bva = analytics.budget_vs_actual(uid, month)
    pct = (bva["actual"].sum() / bva["budget"].sum() * 100) if not bva.empty and bva["budget"].sum() > 0 else None
    active_alerts = db.get_alerts(uid, "active")
    next_month = fc.target_month()
    forecasts = db.get_forecasts(uid, next_month)
    fc_total = sum(f["forecast_amount"] for f in forecasts) if forecasts else None

    head_l, head_r = st.columns([3, 2], vertical_alignment="bottom")
    with head_l:
        st.title(t("Hello, {name}!", name=user["username"]), anchor=False)
        st.caption(t("Here is where your money went in {m}.", m=ui.month_label(month)))
    with head_r:
        with st.container(key="quick_actions", horizontal=True, horizontal_alignment="right"):
            with st.container(key="qa_scan"):
                st.page_link("views/2_Receipts.py", label=t("Scan a receipt"), icon=":material/photo_camera:")
            with st.container(key="qa_all"):
                st.page_link("views/3_Transactions.py", label=t("All transactions"), icon=":material/receipt_long:")
    ui.budget_banner(uid)

    slip_col, glance_col = st.columns([5, 4], gap="large")
    with slip_col:
        lines = []
        if not summary.empty:
            by_total = summary.sort_values("total", ascending=False)
            lines = [(ui.cat_label(r["category_name"]), float(r["total"])) for _, r in by_total.head(5).iterrows()]
            rest = float(by_total["total"].iloc[5:].sum())
            if rest > 0:
                lines.append((t("Other categories"), rest))
        st.markdown(ui.receipt_slip(ui.month_label(month), lines, total, top_cat), unsafe_allow_html=True)
    with glance_col:
        st.markdown(ui.budget_meter(pct), unsafe_allow_html=True)
        with st.container(key="glance"):
            g = st.columns(3)
            g[0].metric(t("Unresolved alerts"), len(active_alerts))
            g[1].metric(t("Transactions recorded"), len(all_tx))
            g[2].metric(t("Forecast next month"), ui.money(fc_total) if fc_total is not None else "—")

    if not all_tx:
        st.info(t("No transactions yet. Upload a receipt or add a transaction manually to get started."))
        st.page_link("views/2_Receipts.py", label=t("Add your first transaction"))
''' + s[b:]
    # bold-text section titles -> real headings
    s = re.sub(r'st\.markdown\(f"\*\*([^"]+?)\*\*"\)', r'st.subheader(f"\1", anchor=False)', s)
    # IPECS mark at the top of the sidebar
    s = swap(s, "with st.sidebar:\n    if user:\n",
             "with st.sidebar:\n    st.markdown(ui.sidebar_brand(), unsafe_allow_html=True)\n    if user:\n")
    return s


edit("app.py", f_app)
print("app.py ok")


# ============================================================ views: login page + report headings
def f_account(s):
    if "brand_header" in s:
        return s
    return swap(s, '''    st.title("IPECS")
    st.caption(t("Intelligent Personal Expense Categorization System"))
''', '''    st.markdown("<style>[data-testid='stMainBlockContainer'], .block-container { max-width: 560px; }</style>",
                unsafe_allow_html=True)                       # narrow, centred login column
    st.markdown(ui.brand_header(), unsafe_allow_html=True)
''')


edit("views/1_Account.py", f_account)
print("1_Account.py ok")


def f_reports(s):
    return re.sub(r"st\.markdown\(f\"\*\*\{t\('(Month-on-month trend|Top merchants)'\)\}\*\*\"\)",
                  r"st.subheader(t('\1'), anchor=False)", s)


edit("views/6_Reports.py", f_reports)
print("6_Reports.py ok")


# ============================================================ components + app icons in the same colours
def recolour(path, pairs):
    p = ROOT / path
    if not p.exists():
        return
    s = p.read_text(encoding="utf-8")
    for old, new in pairs:
        s = s.replace(old, new)
    p.write_text(s, encoding="utf-8")
    print("recoloured", path)


FONT_LINK = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;600&display=swap">\n'
             '<style>')
_mi = ROOT / "components" / "money_input" / "index.html"
if _mi.exists() and "Figtree:wght" not in _mi.read_text(encoding="utf-8"):
    recolour("components/money_input/index.html", [('<meta charset="utf-8">\n<style>', '<meta charset="utf-8">\n' + FONT_LINK)])
recolour("components/money_input/index.html", [
    ('font-family: "Source Sans Pro"', 'font-family: "Figtree", "Source Sans Pro"'),
    ("color: rgb(49, 51, 63); margin-bottom", f"color: {NAVY}; margin-bottom"),
    ("background: rgb(240, 242, 246); border: 1px solid transparent", f"background: #FFFFFF; border: 1px solid {LINE}"),
    ("#box.focus { border-color: rgb(255, 75, 75); }", f"#box.focus {{ border-color: {TEAL}; }}"),
    ("color: rgb(49, 51, 63); text-align", f"color: {NAVY}; text-align"),
])
recolour("components/pwa_install/index.html", [
    ("#2E74B5", TEAL), ("#f4f9fe", "#FFFFFF"), ("#cfe2f5", LINE), ("#1f3b57", NAVY), ("#e6f1fc", "#EAF4F2"),
    ('font-family: "Source Sans Pro"', 'font-family: "Figtree", "Source Sans Pro"'),
])
recolour("pwa/offline.html", [("#2E74B5", TEAL), ("#f4f9fe", MIST), ("#cfe2f5", LINE), ("#1f3b57", NAVY),
                              ("#5b7690", MUTED)])
recolour("pwa/manifest.json", [('"theme_color": "#2E74B5"', f'"theme_color": "{NAVY}"')])

try:                                                       # app icon: navy, white receipt, teal lines
    import cv2
    import numpy as np
    BG, WHITE, TL, INK = (61, 37, 22), (255, 255, 255), (164, 184, 63), (61, 37, 22)     # BGR
    img = np.zeros((512, 512, 3), np.uint8)
    img[:] = BG
    left, right, top, bottom, tooth = 166, 346, 104, 392, 20
    pts, x, down = [(left, top), (right, top), (right, bottom)], right, False
    while x > left:
        x = max(left, x - 18)
        pts.append((x, bottom - (0 if down else tooth)))
        down = not down
    pts.append((left, bottom))
    cv2.fillPoly(img, [np.array(pts, np.int32)], WHITE, lineType=cv2.LINE_AA)
    for y, x2 in ((152, 316), (186, 290), (220, 316), (254, 270)):
        cv2.line(img, (196, y), (x2, y), TL, 12, cv2.LINE_AA)
    cv2.line(img, (196, 296), (316, 296), INK, 6, cv2.LINE_AA)
    cv2.putText(img, "RM", (204, 352), cv2.FONT_HERSHEY_DUPLEX, 1.55, INK, 4, cv2.LINE_AA)
    for name, size in (("icon-512.png", 512), ("icon-192.png", 192), ("apple-touch-icon.png", 180)):
        out = img if size == 512 else cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".png", out)
        if ok and (ROOT / "pwa").exists():
            (ROOT / "pwa" / name).write_bytes(buf.tobytes())
    print("app icons redrawn")
except Exception as e:
    print("app icons kept (could not redraw:", e, ")")


# ============================================================ utils/i18n.py
def f_i18n(s):
    if "Spending so far this month" in s:
        return s
    return s + """

MS.update({
    "Here is where your money went in {m}.": "Ini ke mana wang anda pergi pada {m}.",
    "Scan a receipt": "Imbas resit",
    "All transactions": "Semua transaksi",
    "Spending so far this month": "Perbelanjaan setakat ini bulan ini",
    "No spending recorded yet this month.": "Belum ada perbelanjaan direkodkan bulan ini.",
    "Most frequent category: {c}": "Kategori paling kerap: {c}",
    "Other categories": "Kategori lain",
    "Budget used this month": "Belanjawan digunakan bulan ini",
    "Snap a receipt and IPECS sorts your spending into categories, tracks your budgets and warns you about unusual expenses.":
        "Imbas resit dan IPECS menyusun perbelanjaan anda mengikut kategori, menjejak belanjawan dan memberi amaran tentang perbelanjaan luar biasa.",
})
"""


edit("utils/i18n.py", f_i18n)
print("i18n.py ok")
print("Done. Commit + push, then Reboot app. On the laptop, restart Streamlit to load the new theme.")