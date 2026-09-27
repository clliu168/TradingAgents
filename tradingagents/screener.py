"""Candidate screening ahead of the agent debate.

TradingAgents analyzes the tickers it is given; it does not choose them. This
module narrows a stock universe to a few candidates per market and horizon with
cheap, deterministic rules, so the expensive multi-agent debate only runs on
names that already pass a first filter:

* short-term: recent momentum, trend alignment, volume surge, not overbought;
* long-term: 12-1 month momentum and the 200-day trend, plus business quality,
  growth, leverage and valuation from the vendor's company profile.

Scores are cross-sectional z-scores computed within one market, so Taiwan and
US names are never ranked against each other. Price features are point-in-time
(only bars up to the as-of date); the fundamentals come from the vendor's
current profile and so describe today, which is fine for a live run but not
for a historical backtest.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from tradingagents.dataflows.vendors.yahoo.screening import (
    FUNDAMENTAL_FIELDS,
    fetch_history,
    fetch_profiles,
)

logger = logging.getLogger(__name__)

# Default universes. Edit freely: a symbol with no data is skipped, not fatal.
# Taiwan: large caps close to the 0050 constituents, plus a few TPEx leaders.
TW_UNIVERSE = [
    "2330.TW", "2317.TW", "2454.TW", "2308.TW", "2382.TW", "2881.TW", "2891.TW",
    "2882.TW", "3711.TW", "2412.TW", "2303.TW", "2886.TW", "2884.TW", "2357.TW",
    "1216.TW", "2885.TW", "3231.TW", "2345.TW", "2892.TW", "2890.TW", "5880.TW",
    "2327.TW", "3008.TW", "2379.TW", "6669.TW", "3034.TW", "2301.TW", "2880.TW",
    "2002.TW", "1303.TW", "2603.TW", "3045.TW", "2887.TW", "4938.TW", "1301.TW",
    "2207.TW", "2395.TW", "5871.TW", "3037.TW", "2912.TW", "3661.TW", "2883.TW",
    "1101.TW", "4904.TW", "3017.TW", "2059.TW", "6446.TW", "2383.TW", "2360.TW",
    "6488.TWO", "5274.TWO", "3105.TWO", "8299.TWO", "5347.TWO",
]
# US: large caps across sectors.
US_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "BRK-B", "JPM",
    "V", "MA", "LLY", "UNH", "XOM", "JNJ", "PG", "HD", "COST", "ABBV", "MRK", "PEP",
    "KO", "WMT", "BAC", "CVX", "ORCL", "CRM", "AMD", "ADBE", "NFLX", "TMO", "LIN",
    "MCD", "CSCO", "ACN", "ABT", "DHR", "WFC", "INTU", "TXN", "QCOM", "AMAT", "IBM",
    "CAT", "GE", "NOW", "ISRG", "UBER", "BKNG", "SPGI", "GS", "AXP", "PLTR", "MU",
    "LRCX", "PANW", "ANET", "KLAC", "TSM",
]
UNIVERSES = {"TW": TW_UNIVERSE, "US": US_UNIVERSE}

MIN_BARS = 260  # about one trading year plus a margin, for 200-day and 12-1 features


def market_of(ticker: str) -> str:
    t = ticker.upper()
    return "TW" if t.endswith(".TW") or t.endswith(".TWO") else "US"


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------

def _rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff().dropna()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    last_loss = loss.iloc[-1]
    if last_loss == 0:
        return 100.0
    rs = gain.iloc[-1] / last_loss
    return float(100 - 100 / (1 + rs))


def price_features(ohlcv: pd.DataFrame) -> dict | None:
    """Features from one symbol's daily bars (columns Close, Volume), oldest first.

    Returns None when the history is too short to compute the 200-day and
    12-1 month features honestly.
    """
    df = ohlcv.dropna(subset=["Close"])
    if len(df) < MIN_BARS:
        return None
    close, volume = df["Close"].astype(float), df["Volume"].astype(float)
    last = close.iloc[-1]
    sma20, sma50, sma200 = (close.rolling(n).mean().iloc[-1] for n in (20, 50, 200))
    daily = close.pct_change().dropna()
    vol60 = volume.iloc[-60:].mean()
    return {
        "close": float(last),
        "ret_20d": float(last / close.iloc[-21] - 1),
        "ret_60d": float(last / close.iloc[-61] - 1),
        "ret_12_1": float(close.iloc[-21] / close.iloc[-252] - 1),
        "above_sma200": bool(last > sma200),
        "trend_short": bool(last > sma20 > sma50),
        "pct_vs_sma200": float(last / sma200 - 1),
        "rsi14": _rsi(close.iloc[-120:]),
        "volume_ratio": float(volume.iloc[-5:].mean() / vol60) if vol60 > 0 else np.nan,
        "volatility_60d": float(daily.iloc[-60:].std() * np.sqrt(252)),
        "off_52w_high": float(last / close.iloc[-252:].max() - 1),
        "traded_value_20d": float((close.iloc[-20:] * volume.iloc[-20:]).mean()),
    }


def _z(series: pd.Series) -> pd.Series:
    """Cross-sectional z-score, winsorized at +/-3; missing values score 0 (neutral)."""
    s = pd.to_numeric(series, errors="coerce").astype(float)
    std = s.std(ddof=0)
    if not np.isfinite(std) or std == 0:
        return pd.Series(0.0, index=s.index)
    return ((s - s.mean()) / std).clip(-3, 3).fillna(0.0)


def score_short(features: pd.DataFrame) -> pd.Series:
    f = features
    overbought = (f["rsi14"] - 70).clip(lower=0)
    return (
        0.35 * _z(f["ret_20d"])
        + 0.20 * _z(f["ret_60d"])
        + 0.15 * _z(f["volume_ratio"])
        + 0.20 * _z(f["trend_short"].astype(float))
        - 0.10 * _z(overbought)
    )


def score_long(features: pd.DataFrame) -> pd.Series:
    f = features
    # Valuation: earnings yield (1/forward PE) so a loss-maker ranks last
    # rather than looking "cheap" on a negative PE.
    pe = pd.to_numeric(f.get("forwardPE"), errors="coerce")
    earnings_yield = (1 / pe).where(pe > 0, other=-0.05)
    return (
        0.25 * _z(f["ret_12_1"])
        + 0.15 * _z(f["above_sma200"].astype(float))
        + 0.15 * _z(f.get("returnOnEquity"))
        + 0.10 * _z(f.get("revenueGrowth"))
        + 0.10 * _z(f.get("earningsGrowth"))
        + 0.10 * _z(f.get("profitMargins"))
        - 0.05 * _z(f.get("debtToEquity"))
        + 0.10 * _z(earnings_yield)
    )


# ---------------------------------------------------------------------------
# Reasons (deterministic, in Traditional Chinese)
# ---------------------------------------------------------------------------

def _pct(x) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:+.1%}"


def short_reason(row: pd.Series) -> str:
    parts = [f"近 20 日 {_pct(row['ret_20d'])}、近 60 日 {_pct(row['ret_60d'])}"]
    if row["trend_short"]:
        parts.append("股價站上 20 日線且 20 日線高於 50 日線（短期多頭排列）")
    if np.isfinite(row["volume_ratio"]):
        parts.append(f"近 5 日均量為 60 日均量的 {row['volume_ratio']:.1f} 倍")
    parts.append(f"RSI(14) {row['rsi14']:.0f}" + ("，已偏過熱" if row["rsi14"] >= 70 else ""))
    return "；".join(parts) + "。"


def long_reason(row: pd.Series) -> str:
    parts = [f"過去 12 個月（扣除最近 1 個月）{_pct(row['ret_12_1'])}，"
             f"{'位於' if row['above_sma200'] else '低於'} 200 日線（{_pct(row['pct_vs_sma200'])}）"]
    fund = []
    for key, label in (("returnOnEquity", "ROE"), ("revenueGrowth", "營收成長"),
                       ("earningsGrowth", "獲利成長"), ("profitMargins", "淨利率")):
        v = row.get(key)
        if v is not None and np.isfinite(v):
            fund.append(f"{label} {v:.1%}")
    pe = row.get("forwardPE")
    if pe is not None and np.isfinite(pe):
        fund.append(f"預估本益比 {pe:.1f}" if pe > 0 else "預估獲利為負")
    if fund:
        parts.append("、".join(fund))
    return "；".join(parts) + "。"


# ---------------------------------------------------------------------------
# Screening
# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    ticker: str
    name: str
    market: str
    horizon: str
    score: float
    rank: int
    reason: str
    features: dict = field(default_factory=dict)


def build_feature_table(
    tickers: list[str],
    as_of: str,
    history_fn: Callable[[list[str], str], dict[str, pd.DataFrame]] = fetch_history,
    profile_fn: Callable[[Iterable[str]], dict[str, dict]] = fetch_profiles,
    min_traded_value: dict[str, float] | None = None,
) -> pd.DataFrame:
    """One row per ticker with price features and profile fields.

    Tickers without enough history, or below the market's liquidity floor
    (average daily traded value over 20 days, in local currency), are dropped.
    """
    floors = {"TW": 5e7, "US": 2e7} if min_traded_value is None else min_traded_value
    history = history_fn(tickers, as_of)
    rows = {}
    for t, df in history.items():
        feats = price_features(df)
        if feats is None:
            logger.info("Skipping %s: under %d bars", t, MIN_BARS)
            continue
        if feats["traded_value_20d"] < floors.get(market_of(t), 0):
            logger.info("Skipping %s: below liquidity floor", t)
            continue
        rows[t] = feats
    if not rows:
        return pd.DataFrame()
    table = pd.DataFrame.from_dict(rows, orient="index")
    profiles = profile_fn(table.index)
    prof = pd.DataFrame.from_dict(profiles, orient="index").reindex(table.index)
    for col in (*FUNDAMENTAL_FIELDS, "name"):
        table[col] = prof.get(col, None)
    for col in FUNDAMENTAL_FIELDS:
        table[col] = pd.to_numeric(table[col], errors="coerce")
    table["name"] = table["name"].fillna(pd.Series(table.index, index=table.index))
    table["market"] = [market_of(t) for t in table.index]
    return table


def screen(
    table: pd.DataFrame,
    horizon: str,
    top_n: int = 3,
    markets: Iterable[str] = ("TW", "US"),
) -> list[Candidate]:
    """Top ``top_n`` candidates per market for ``horizon`` ("short" or "long")."""
    if table.empty:
        return []
    scorer, reasoner = (score_short, short_reason) if horizon == "short" else (score_long, long_reason)
    picks: list[Candidate] = []
    for market in markets:
        sub = table[table["market"] == market]
        if horizon == "long":
            # Too little fundamental coverage makes the quality score meaningless.
            coverage = sub[list(FUNDAMENTAL_FIELDS)].notna().sum(axis=1)
            sub = sub[coverage >= 3]
        if len(sub) < 2:
            continue
        scores = scorer(sub).sort_values(ascending=False)
        for rank, (t, s) in enumerate(scores.head(top_n).items(), start=1):
            row = sub.loc[t]
            picks.append(Candidate(
                ticker=t, name=str(row["name"]), market=market, horizon=horizon,
                score=float(s), rank=rank, reason=reasoner(row),
                features={k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()},
            ))
    return picks
