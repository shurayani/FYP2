"""One-time patch #8:
  * forecast is back to the report's rule: at least 3 COMPLETE months per category (weekly mode removed);
    only the last 12 months are used, so an old receipt (e.g. dated 2017) cannot distort the forecast
  * receipts whose item names are only codes/numbers: those items are NOT guessed - they use the shop's category
    and the form tells you which items to check
Run once from the project folder:   python patch_v8.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def edit(path, fn):
    p = ROOT / path
    p.write_text(fn(p.read_text(encoding="utf-8")), encoding="utf-8")


def swap(s, old, new):
    assert old in s, "anchor not found: " + old[:70]
    return s.replace(old, new, 1)


# ============================================================ src/forecast.py (monthly only, 12-month window)
(ROOT / "src" / "forecast.py").write_text('''"""Spending forecast (Module 8, FR11, Section 5.6.8).

Primary layer : Prophet, fully offline - next-month forecast per category with confidence interval.
    A category needs at least MIN_MONTHS_FOR_FORECAST COMPLETE months of history (the current month is not
    complete, so it is not used). Only the last MAX_HISTORY_MONTHS months are used.
Secondary layer: optional Gemini insights (utils/gemini_helper) when online; skipped silently otherwise."""
import logging
from datetime import date

import pandas as pd

from src import analytics, db_manager as db
from utils import gemini_helper
from utils.config import MIN_MONTHS_FOR_FORECAST

MAX_HISTORY_MONTHS = 12

logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)


def target_month() -> str:
    """The forecast target is the calendar month after the current one."""
    return analytics.add_months(analytics.month_str(date.today()), 1)


def _category_monthly(df: pd.DataFrame, category_id: str, last_complete: str) -> pd.DataFrame:
    first_allowed = analytics.add_months(last_complete, -(MAX_HISTORY_MONTHS - 1))
    month = df["date"].dt.strftime("%Y-%m")
    d = df[(df["category_id"] == category_id) & (month <= last_complete) & (month >= first_allowed)].copy()
    if d.empty:
        return pd.DataFrame(columns=["ds", "y"])
    d["m"] = d["date"].dt.to_period("M")
    g = d.groupby("m")["amount"].sum()
    full = pd.period_range(g.index.min(), pd.Period(last_complete), freq="M")
    g = g.reindex(full, fill_value=0.0)
    return pd.DataFrame({"ds": g.index.to_timestamp(), "y": g.values})


def prophet_forecast(series: pd.DataFrame, periods: int):
    """Fit Prophet on monthly totals and return (yhat, lower, upper) for the last future month."""
    from prophet import Prophet
    logging.getLogger("cmdstanpy").setLevel(logging.WARNING)     # silence per-fit INFO chatter
    m = Prophet(yearly_seasonality=False, weekly_seasonality=False, daily_seasonality=False,
                interval_width=0.8)
    m.fit(series)
    future = m.make_future_dataframe(periods=periods, freq="MS")
    fc = m.predict(future).iloc[-1]
    return max(0.0, float(fc["yhat"])), max(0.0, float(fc["yhat_lower"])), max(0.0, float(fc["yhat_upper"]))


def generate_forecasts(user_id) -> dict:
    """(Re)calculate next-month forecasts for every category with enough history and save them.
    Returns {"saved": n, "skipped": [category names], "target": month}."""
    df = analytics.transactions_df(user_id)
    target = target_month()
    saved, skipped = 0, []
    if df.empty:
        return {"saved": 0, "skipped": [], "target": target}
    last_complete = analytics.add_months(analytics.month_str(date.today()), -1)
    for _, cat in df[["category_id", "category_name"]].drop_duplicates().iterrows():
        series = _category_monthly(df, cat["category_id"], last_complete)
        if len(series) < MIN_MONTHS_FOR_FORECAST or series["y"].sum() <= 0:
            skipped.append(cat["category_name"])
            continue
        yhat, lo, hi = prophet_forecast(series, 2)       # last complete month -> this month -> target month
        db.save_forecast(user_id, cat["category_id"], target, yhat, lo, hi)
        saved += 1
    return {"saved": saved, "skipped": skipped, "target": target}


def forecast_summary(user_id, month: str) -> dict:
    """Structured summary sent to Gemini for insights."""
    f = db.get_forecasts(user_id, month)
    cur = analytics.monthly_summary(user_id, analytics.month_str(date.today()))
    budgets = db.get_budgets(user_id, month)
    return {
        "forecast_month": month,
        "forecasts": [{"category": x["category_name"], "forecast": round(x["forecast_amount"], 2),
                       "low": round(x["confidence_lower"] or 0, 2), "high": round(x["confidence_upper"] or 0, 2)}
                      for x in f],
        "current_month_actual": [{"category": r["category_name"], "total": round(float(r["total"]), 2)}
                                 for _, r in cur.iterrows()],
        "budgets": [{"category": b["category_name"], "amount": b["budget_amount"]} for b in budgets],
    }


def get_ai_insights(user_id, month: str, language: str = "English"):
    """Optional layer. Returns text, or None if offline / no key / request fails (silent skip)."""
    from src.ocr_module import is_online
    if not gemini_helper.is_configured() or not is_online():
        return None
    try:
        return gemini_helper.generate_insights(forecast_summary(user_id, month), language)
    except Exception:
        return None
''', encoding="utf-8")
print("forecast.py restored (3 complete months, last 12 months only)")


# ============================================================ pages/8_Forecast.py (months-only messages)
def f_forecast_page(s):
    if "last 12 months" in s:
        return s
    a = s.index('st.caption(t("Next-month forecasts')
    b = s.index('if st.button(t("Recalculate forecasts")')
    s = s[:a] + ('st.caption(t("Next-month forecasts per category are computed offline with Prophet from your last 12 months '
                 '(at least {n} complete months per category; the current month is not counted).",\n'
                 '             n=MIN_MONTHS_FOR_FORECAST))\n\n') + s[b:]
    a = s.index('st.warning(t("Not enough history')
    b = s.index("\n", a)
    s = s[:a] + ('st.warning(t("Not enough history to forecast yet. Record transactions across at least {n} different months.", '
                 'n=MIN_MONTHS_FOR_FORECAST))') + s[b:]
    return s


edit("pages/8_Forecast.py", f_forecast_page)


# ============================================================ utils/gemini_helper.py: do not guess unreadable items
def f_gemini(s):
    if "you cannot understand, set its category to null" in s:
        return s
    return swap(s, '"station is food/groceries, not transport). If nothing fits perfectly use the closest category. "',
                '"station is food/groceries, not transport). If nothing fits perfectly use the closest category, but if an "\n'
                '                "item name is only a code, number or abbreviation you cannot understand, set its category to null "\n'
                '                "instead of guessing. "')


edit("utils/gemini_helper.py", f_gemini)


# ============================================================ src/preprocessor.py: code-only names never get a guessed category
def f_pre(s):
    if "only a code / number" in s:
        return s
    return swap(s, '        out.append({"name": str(it.get("name") or "").strip()[:60], "amount": round(amt, 2),\n'
                   '                    "category": lookup.get(str(it.get("category") or "").strip().lower())})\n',
                '        name = str(it.get("name") or "").strip()[:60]\n'
                '        cat = lookup.get(str(it.get("category") or "").strip().lower())\n'
                '        if not re.search(r"[A-Za-z]{3,}", name):      # only a code / number: any category would be a guess\n'
                '            cat = None\n'
                '        out.append({"name": name, "amount": round(amt, 2), "category": cat})\n')


edit("src/preprocessor.py", f_pre)


# ============================================================ pages/2_Receipts.py: tell the user which items to check
def f_receipts(s):
    if "could not be categorised" in s:
        return s
    anchor = '    edited = st.data_editor(\n        base, num_rows="dynamic", hide_index=True, width="stretch", key=f"{key}_items",'
    new = ('    unknown = sum(1 for i in items if not (i["category"] and ui.cat_label(i["category"]) in cats))\n'
           '    if unknown:\n'
           '        st.warning(t("{n} item(s) could not be categorised because the name is unreadable or only a code. '
           'They use the shop\'s category - please check them.", n=unknown))\n')
    return swap(s, anchor, new + anchor)


edit("pages/2_Receipts.py", f_receipts)


# ============================================================ utils/i18n.py
def f_i18n(s):
    if "could not be categorised" in s:
        return s
    return s + '''

MS.update({
    "Next-month forecasts per category are computed offline with Prophet from your last 12 months (at least {n} complete months per category; the current month is not counted).":
        "Ramalan bulan depan bagi setiap kategori dikira secara luar talian dengan Prophet daripada 12 bulan terakhir anda (sekurang-kurangnya {n} bulan lengkap setiap kategori; bulan semasa tidak dikira).",
    "{n} item(s) could not be categorised because the name is unreadable or only a code. They use the shop's category - please check them.":
        "{n} barang tidak dapat dikategorikan kerana nama tidak dapat dibaca atau hanya kod. Ia guna kategori kedai - sila semak.",
})
'''


edit("utils/i18n.py", f_i18n)
print("Done. Restart Streamlit.")