"""Monthly spending report as a PDF (patch #23). Uses reportlab; the data comes from analytics.build_report()."""
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
