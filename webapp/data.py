"""Market data for the web app: prices, company profiles and news from Yahoo Finance.

Everything is cached by Streamlit for a few minutes so page switches are fast.
Set ``TA_WEB_DEMO=1`` to use deterministic synthetic data instead (no network),
which is how the app is tested.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import streamlit as st

from tradingagents.dataflows.vendors.yahoo.news import _extract_article_data

DEMO = os.getenv("TA_WEB_DEMO") == "1"

INDICES = {
    "^TWII": "台灣加權指數",
    "^TWOII": "櫃買指數",
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq",
    "^DJI": "道瓊工業",
    "^SOX": "費城半導體",
    "^VIX": "VIX 恐慌指數",
    "TWD=X": "美元/台幣",
    "^TNX": "美國 10 年期公債殖利率",
}

# Yahoo serves ^TWOII quotes but often no history; fall back to the 富櫃50 ETF.
INDEX_PROXIES = {"^TWOII": "006201.TWO"}


@st.cache_data(ttl=600, show_spinner=False)
def resolve_index(sym: str) -> str:
    """The symbol that actually has price history: the index, else its proxy."""
    if DEMO or sym not in INDEX_PROXIES:
        return sym
    return sym if not history(sym, 45, warmup=0).empty else INDEX_PROXIES[sym]


def index_history(sym: str, days: int) -> tuple[str, pd.DataFrame]:
    used = resolve_index(sym)
    return used, history(used, days, warmup=0)


PERIOD_DAYS = {"1 個月": 31, "3 個月": 92, "6 個月": 183, "1 年": 366, "2 年": 731, "5 年": 1827}


def _seed(key: str) -> int:
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16)


def _demo_history(ticker: str, days: int) -> pd.DataFrame:
    rng = np.random.default_rng(_seed(ticker))
    n = max(int(days * 252 / 365), 30) + 260
    drift = rng.normal(0.0004, 0.0006)
    ret = rng.normal(drift, 0.015, n)
    close = (50 + _seed(ticker) % 900) * np.cumprod(1 + ret)
    open_ = close * (1 + rng.normal(0, 0.004, n))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.006, n)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.006, n)))
    vol = rng.lognormal(15, 0.35, n)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize() - pd.Timedelta(days=1), periods=n)
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": vol}, index=idx)


@st.cache_data(ttl=600, show_spinner=False)
def history(ticker: str, days: int, warmup: int = 260) -> pd.DataFrame:
    """Daily OHLCV for the last ``days`` calendar days plus ``warmup`` bars for indicators."""
    if DEMO:
        return _demo_history(ticker, days)
    import yfinance as yf

    start = (datetime.now() - timedelta(days=days + int(warmup * 1.5))).strftime("%Y-%m-%d")
    try:
        df = yf.Ticker(ticker).history(start=start, auto_adjust=True)
    except Exception:  # noqa: BLE001 — an unknown or unserved symbol reads as no data
        return pd.DataFrame()
    if df.empty:
        return df
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])


@st.cache_data(ttl=600, show_spinner=False)
def closes(tickers: tuple[str, ...], days: int) -> pd.DataFrame:
    """Close prices, one column per ticker, over the last ``days`` calendar days."""
    frames = {}
    for t in tickers:
        h = history(t, days, warmup=0)
        if not h.empty:
            frames[t] = h["Close"]
    if not frames:
        return pd.DataFrame()
    df = pd.DataFrame(frames).sort_index()
    cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=days)
    return df[df.index >= cutoff].ffill()


@st.cache_data(ttl=3600, show_spinner=False)
def profile(ticker: str) -> dict:
    """Company profile and key statistics (Yahoo's current values)."""
    if DEMO:
        rng = np.random.default_rng(_seed(ticker + "p"))
        return {
            "shortName": f"Demo {ticker}", "longName": f"Demo Company {ticker}",
            "sector": "Technology", "industry": "Semiconductors", "country": "Taiwan",
            "currency": "TWD" if ".TW" in ticker else "USD",
            "marketCap": float(rng.uniform(1e10, 3e12)), "trailingPE": float(rng.uniform(10, 40)),
            "forwardPE": float(rng.uniform(10, 35)), "priceToBook": float(rng.uniform(1, 10)),
            "returnOnEquity": float(rng.uniform(0.05, 0.35)), "profitMargins": float(rng.uniform(0.05, 0.4)),
            "revenueGrowth": float(rng.uniform(-0.1, 0.4)), "earningsGrowth": float(rng.uniform(-0.2, 0.5)),
            "debtToEquity": float(rng.uniform(5, 150)), "dividendYield": float(rng.uniform(0, 4)),
            "beta": float(rng.uniform(0.6, 1.6)), "fiftyTwoWeekHigh": 1000.0, "fiftyTwoWeekLow": 500.0,
            "longBusinessSummary": "這是 demo 模式的示範公司描述。實際執行時會顯示 Yahoo Finance 的公司簡介。",
            "website": "https://example.com",
        }
    import yfinance as yf

    try:
        return yf.Ticker(ticker).info or {}
    except Exception:  # noqa: BLE001 — the page shows what it has
        return {}


def _demo_news(key: str, n: int = 8) -> list[dict]:
    now = datetime.now(timezone.utc)
    return [{
        "title": f"[Demo] {key} 相關新聞標題 {i + 1}",
        "summary": "這是 demo 模式的新聞摘要。實際執行時會顯示 Yahoo Finance 新聞的內容摘要。",
        "publisher": ["Reuters", "Bloomberg", "CNBC", "經濟日報"][i % 4],
        "link": f"https://example.com/news/{abs(_seed(key)) % 9999}/{i}",
        "pub_date": now - timedelta(hours=5 * i + 1),
    } for i in range(n)]


@st.cache_data(ttl=900, show_spinner=False)
def ticker_news(ticker: str, count: int = 15) -> list[dict]:
    """Latest news for one ticker, newest first."""
    if DEMO:
        return _demo_news(ticker)
    import yfinance as yf

    try:
        raw = yf.Ticker(ticker).get_news(count=count) or []
    except Exception:  # noqa: BLE001
        return []
    items = [_extract_article_data(a) for a in raw]
    return _sorted_unique(items)


@st.cache_data(ttl=900, show_spinner=False)
def search_news(queries: tuple[str, ...], per_query: int = 8) -> list[dict]:
    """Market news from Yahoo search queries, de-duplicated, newest first."""
    if DEMO:
        return [a for q in queries for a in _demo_news(q, 3)]
    import yfinance as yf

    items = []
    for q in queries:
        try:
            s = yf.Search(query=q, news_count=per_query, enable_fuzzy_query=True)
            items += [_extract_article_data(a) for a in (s.news or [])]
        except Exception:  # noqa: BLE001
            continue
    return _sorted_unique(items)


def _sorted_unique(items: list[dict]) -> list[dict]:
    seen, out = set(), []
    for a in items:
        if a.get("title") and a["title"] not in seen:
            seen.add(a["title"])
            out.append(a)
    far_past = datetime(1970, 1, 1, tzinfo=timezone.utc)
    return sorted(out, key=lambda a: a.get("pub_date") or far_past, reverse=True)


# Tickers whose own news feed is added to a market tab (search alone skews to US stories).
MARKET_NEWS_TICKERS = {
    "台股": ("2330.TW", "2454.TW", "2317.TW", "TSM", "^TWII"),
    "美股": ("^GSPC", "SPY", "QQQ"),
    "總經與地緣": (),
}


def market_news(topic: str) -> list[dict]:
    items = list(search_news(MARKET_NEWS_QUERIES[topic]))
    for t in MARKET_NEWS_TICKERS.get(topic, ()):
        items += ticker_news(t, 10)
    return _sorted_unique(items)


MARKET_NEWS_QUERIES = {
    "台股": ("Taiwan stock market TAIEX", "Taiwan stocks Taipei", "Taiwan economy exports central bank"),
    "美股": ("stock market today", "Federal Reserve interest rates", "Nasdaq tech stocks earnings"),
    "總經與地緣": ("inflation CPI jobs report", "oil prices OPEC", "US China trade tariffs"),
}
