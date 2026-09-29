"""Taiwan market data from FinMind (https://finmindtrade.com): institutional
investor flows, margin trading, monthly revenue and dividends.

FinMind needs a free account token: put FINMIND_TOKEN=... in .env.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from tradingagents.dataflows.vendors.finmind import (
    GROUPS as INVESTOR_NAMES,  # noqa: F401
    fetch as _fetch,
    net_flows,
    revenue_table,
    taiwan_stock_id,
)
from webapp.data import DEMO
from webapp.jobs import ROOT


def stock_id(ticker: str) -> str | None:
    return taiwan_stock_id(ticker)


def fetch(dataset: str, sid: str, start: str, end: str | None = None) -> pd.DataFrame:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    return _fetch(dataset, sid, start, end)


def _demo(dataset: str, sid: str, days: int) -> pd.DataFrame:
    import numpy as np

    rng = np.random.default_rng(int(sid) if sid.isdigit() else 1)
    idx = pd.bdate_range(end=date.today() - timedelta(days=1), periods=days)
    if dataset == "flows":
        rows = [{"date": d, "name": n, "buy": abs(rng.normal(8e6, 3e6)), "sell": abs(rng.normal(8e6, 3e6))}
                for d in idx for n in ("Foreign_Investor", "Investment_Trust", "Dealer_self")]
        return pd.DataFrame(rows)
    if dataset == "margin":
        return pd.DataFrame({"date": idx, "MarginPurchaseTodayBalance": 20000 + rng.normal(0, 300, days).cumsum(),
                             "ShortSaleTodayBalance": 1500 + rng.normal(0, 50, days).cumsum()})
    months = pd.date_range(end=date.today(), periods=26, freq="MS")
    rev = 2e11 * (1 + np.arange(26) * 0.02) * (1 + rng.normal(0, 0.05, 26))
    return pd.DataFrame({"date": months + pd.Timedelta(days=9), "revenue": rev,
                         "revenue_year": months.year, "revenue_month": months.month})


@st.cache_data(ttl=3600, show_spinner=False)
def institutional_flows(sid: str, days: int = 60) -> pd.DataFrame:
    """Daily net buy (shares) per investor group: columns 外資, 投信, 自營商, 合計."""
    start = (date.today() - timedelta(days=int(days * 1.6))).isoformat()
    raw = _demo("flows", sid, days) if DEMO else fetch("TaiwanStockInstitutionalInvestorsBuySell", sid, start)
    df = net_flows(raw)
    return df.tail(days)


@st.cache_data(ttl=3600, show_spinner=False)
def margin(sid: str, days: int = 120) -> pd.DataFrame:
    """Margin purchase and short sale balances (張)."""
    start = (date.today() - timedelta(days=int(days * 1.6))).isoformat()
    raw = _demo("margin", sid, days) if DEMO else fetch("TaiwanStockMarginPurchaseShortSale", sid, start)
    if raw.empty:
        return raw
    df = raw[["date", "MarginPurchaseTodayBalance", "ShortSaleTodayBalance"]].copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").rename(columns={"MarginPurchaseTodayBalance": "融資餘額",
                                              "ShortSaleTodayBalance": "融券餘額"})
    df["券資比"] = df["融券餘額"] / df["融資餘額"].replace(0, pd.NA)
    return df.tail(days)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def month_revenue(sid: str, months: int = 26) -> pd.DataFrame:
    """Monthly revenue with YoY and MoM growth, indexed by the revenue month."""
    start = (date.today() - timedelta(days=31 * (months + 13))).isoformat()
    raw = _demo("revenue", sid, months) if DEMO else fetch("TaiwanStockMonthRevenue", sid, start)
    df = revenue_table(raw)
    if df.empty:
        return df
    return df.tail(months)


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def dividends(sid: str) -> pd.DataFrame:
    """Announced dividends with ex-dividend dates (cash and stock)."""
    if DEMO:
        return pd.DataFrame({"year": ["114年"], "現金股利": [5.0], "除息交易日": [date.today() + timedelta(days=20)],
                             "發放日": [date.today() + timedelta(days=45)]})
    raw = fetch("TaiwanStockDividend", sid, (date.today() - timedelta(days=500)).isoformat())
    if raw.empty:
        return raw
    df = pd.DataFrame({
        "year": raw["year"],
        "現金股利": raw["CashEarningsDistribution"].astype(float) + raw["CashStatutorySurplus"].astype(float),
        "股票股利": raw["StockEarningsDistribution"].astype(float) + raw["StockStatutorySurplus"].astype(float),
        "除息交易日": pd.to_datetime(raw["CashExDividendTradingDate"], errors="coerce"),
        "除權交易日": pd.to_datetime(raw["StockExDividendTradingDate"], errors="coerce"),
        "發放日": pd.to_datetime(raw["CashDividendPaymentDate"], errors="coerce"),
    })
    return df.sort_values("除息交易日", ascending=False)
