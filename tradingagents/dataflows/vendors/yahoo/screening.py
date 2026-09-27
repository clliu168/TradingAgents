"""Bulk price history and company profiles for the candidate screener.

Kept in the data layer with the other Yahoo calls, so vendor failures stay here.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pandas as pd
import yfinance as yf

from tradingagents.dataflows.vendors.yahoo.ohlcv import yf_retry

logger = logging.getLogger(__name__)

FUNDAMENTAL_FIELDS = (
    "returnOnEquity", "revenueGrowth", "earningsGrowth", "profitMargins",
    "debtToEquity", "forwardPE",
)


def fetch_history(tickers: list[str], as_of: str) -> dict[str, pd.DataFrame]:
    """Daily bars up to and including ``as_of`` for each ticker (point-in-time)."""
    end = (datetime.strptime(as_of, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    start = (datetime.strptime(as_of, "%Y-%m-%d") - timedelta(days=420)).strftime("%Y-%m-%d")
    raw = yf_retry(lambda: yf.download(tickers, start=start, end=end, auto_adjust=True,
                      group_by="ticker", threads=True, progress=False))
    out = {}
    for t in tickers:
        try:
            df = raw[t] if isinstance(raw.columns, pd.MultiIndex) else raw
            df = df[["Close", "Volume"]].dropna(subset=["Close"])
            if not df.empty:
                out[t] = df
        except KeyError:
            logger.info("No price history for %s", t)
    return out


def fetch_profiles(tickers: Iterable[str]) -> dict[str, dict]:
    """Current company profile per ticker (name + the fundamental fields)."""
    def one(t):
        try:
            info = yf.Ticker(t).info or {}
        except Exception as exc:  # noqa: BLE001 — a missing profile is not fatal
            logger.info("No profile for %s: %s", t, exc)
            info = {}
        rec = {k: info.get(k) for k in FUNDAMENTAL_FIELDS}
        rec["name"] = info.get("shortName") or info.get("longName") or t
        return t, rec

    with ThreadPoolExecutor(max_workers=8) as pool:
        return dict(pool.map(one, list(tickers)))
