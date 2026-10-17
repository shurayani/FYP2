"""Spending forecast (Module 8, FR11, Section 5.6.8).

Primary layer : Prophet, fully offline - next-month forecast per category with confidence interval.
Secondary layer: optional Gemini insights (utils/gemini_helper) when online; skipped silently otherwise."""
import logging
from datetime import date

import pandas as pd

from src import analytics, db_manager as db
from utils import gemini_helper
from utils.config import MIN_MONTHS_FOR_FORECAST

logging.getLogger("cmdstanpy").setLevel(logging.WARNING)
logging.getLogger("prophet").setLevel(logging.WARNING)


def target_month() -> str:
    """The forecast target is the calendar month after the current one."""
    return analytics.add_months(analytics.month_str(date.today()), 1)


def _category_monthly(df: pd.DataFrame, category_id: str, last_complete: str) -> pd.DataFrame:
    d = df[(df["category_id"] == category_id) & (df["date"].dt.strftime("%Y-%m") <= last_complete)].copy()
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
    Returns {"saved": n, "skipped": [category names]}."""
    df = analytics.transactions_df(user_id)
    target = target_month()
    saved, skipped = 0, []
    if df.empty:
        return {"saved": 0, "skipped": [], "target": target}
    last_complete = analytics.add_months(analytics.month_str(date.today()), -1)
    periods = 2          # last complete month -> current month -> target month
    for _, cat in df[["category_id", "category_name"]].drop_duplicates().iterrows():
        series = _category_monthly(df, cat["category_id"], last_complete)
        if len(series) < MIN_MONTHS_FOR_FORECAST or series["y"].sum() <= 0:
            skipped.append(cat["category_name"])
            continue
        yhat, lo, hi = prophet_forecast(series, periods)
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
