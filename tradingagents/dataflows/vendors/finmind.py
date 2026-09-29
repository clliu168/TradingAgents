"""FinMind (Taiwan market data): institutional flows, margin, monthly revenue.

Used two ways: by the web app for charts, and at run start to give the agents a
short, point-in-time Taiwan data brief (as of the analysis date) for .TW/.TWO
tickers, which Yahoo's English news and fundamentals largely miss.

Needs FINMIND_TOKEN in the environment (free account at finmindtrade.com).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

import pandas as pd

logger = logging.getLogger(__name__)
API = "https://api.finmindtrade.com/api/v4/data"
GROUPS = {"Foreign_Investor": "外資", "Foreign_Dealer_Self": "外資", "Investment_Trust": "投信",
          "Dealer_self": "自營商", "Dealer_Hedging": "自營商", "Dealer": "自營商"}


class FinMindError(RuntimeError):
    pass


def taiwan_stock_id(ticker: str) -> str | None:
    t = ticker.upper()
    for suf in (".TWO", ".TW"):
        if t.endswith(suf):
            return t[: -len(suf)]
    return None


def fetch(dataset: str, sid: str, start: str, end: str | None = None) -> pd.DataFrame:
    import requests

    params = {"dataset": dataset, "data_id": sid, "start_date": start}
    if end:
        params["end_date"] = end
    tok = os.environ.get("FINMIND_TOKEN", "")
    headers = {"Authorization": f"Bearer {tok}"} if tok else {}
    r = requests.get(API, params=params, headers=headers, timeout=30)
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code != 200 or body.get("status") not in (200, None):
        raise FinMindError(body.get("msg") or f"HTTP {r.status_code}")
    return pd.DataFrame(body.get("data", []))


def net_flows(raw: pd.DataFrame) -> pd.DataFrame:
    """Daily net buy in 張 per investor group, plus 合計."""
    if raw.empty:
        return raw
    raw = raw.copy()
    raw["group"] = raw["name"].map(GROUPS).fillna(raw["name"])
    raw["net"] = raw["buy"].astype(float) - raw["sell"].astype(float)
    df = raw.pivot_table(index="date", columns="group", values="net", aggfunc="sum").fillna(0)
    df.index = pd.to_datetime(df.index)
    df = (df / 1000).round(0)
    df["合計"] = df.sum(axis=1)
    return df.sort_index()


def revenue_table(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return raw
    df = raw.copy()
    df["月份"] = pd.to_datetime({"year": df["revenue_year"].astype(int), "month": df["revenue_month"].astype(int), "day": 1})
    df = df.drop_duplicates("月份").set_index("月份").sort_index()
    df["營收（億）"] = df["revenue"].astype(float) / 1e8
    df["年增率"] = df["營收（億）"].pct_change(12)
    df["月增率"] = df["營收（億）"].pct_change(1)
    df["公布日"] = pd.to_datetime(df["date"])
    return df[["營收（億）", "年增率", "月增率", "公布日"]]


def taiwan_brief(ticker: str, as_of: str) -> str:
    """A few lines of Taiwan-specific data known on ``as_of``; '' when unavailable."""
    sid = taiwan_stock_id(ticker)
    if not sid or not os.environ.get("FINMIND_TOKEN"):
        return ""
    end = datetime.strptime(as_of, "%Y-%m-%d")
    lines = []
    try:
        flows = net_flows(fetch("TaiwanStockInstitutionalInvestorsBuySell", sid,
                                (end - timedelta(days=45)).strftime("%Y-%m-%d"), as_of))
        if not flows.empty:
            f5, f20 = flows.tail(5).sum(), flows.tail(20).sum()
            parts = [f"{g} {f5.get(g, 0):+,.0f} / {f20.get(g, 0):+,.0f}" for g in ("外資", "投信", "自營商")]
            lines.append("Institutional net buy in lots of 1,000 shares (last 5 / last 20 trading days, "
                         f"to {flows.index[-1]:%Y-%m-%d}): " + "; ".join(parts) + ".")
        mg = fetch("TaiwanStockMarginPurchaseShortSale", sid, (end - timedelta(days=45)).strftime("%Y-%m-%d"), as_of)
        if not mg.empty and "MarginPurchaseTodayBalance" in mg:
            mg = mg.sort_values("date")
            m0, m1 = float(mg["MarginPurchaseTodayBalance"].iloc[0]), float(mg["MarginPurchaseTodayBalance"].iloc[-1])
            s1 = float(mg["ShortSaleTodayBalance"].iloc[-1])
            lines.append(f"Margin purchase balance {m1:,.0f} lots ({(m1 / m0 - 1) if m0 else 0:+.1%} over ~30 days), "
                         f"short sale balance {s1:,.0f} lots, as of {mg['date'].iloc[-1]}.")
        rev = revenue_table(fetch("TaiwanStockMonthRevenue", sid, (end - timedelta(days=500)).strftime("%Y-%m-%d"),
                                  as_of))
        rev = rev[rev["公布日"] <= end] if not rev.empty else rev
        if not rev.empty:
            tail = rev.tail(3)
            lines.append("Monthly revenue (NT$100M, YoY): " + "; ".join(
                f"{i:%Y-%m} {r['營收（億）']:,.1f} ({r['年增率']:+.1%})" if pd.notna(r["年增率"])
                else f"{i:%Y-%m} {r['營收（億）']:,.1f}" for i, r in tail.iterrows()) + ".")
    except Exception as exc:  # noqa: BLE001 — the brief is optional context, never a blocker
        logger.info("FinMind brief for %s unavailable: %s", ticker, exc)
    if not lines:
        return ""
    return " Taiwan market data (FinMind, point-in-time): " + " ".join(lines)
