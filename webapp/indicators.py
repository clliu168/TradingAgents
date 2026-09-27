"""Technical indicators on a daily OHLCV frame (columns Open, High, Low, Close, Volume)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with moving averages, Bollinger bands, MACD and RSI added."""
    out = df.copy()
    close = out["Close"].astype(float)
    for n in (5, 20, 60, 120, 240):
        out[f"SMA{n}"] = close.rolling(n).mean()
    mid = close.rolling(20).mean()
    std = close.rolling(20).std(ddof=0)
    out["BB_mid"], out["BB_up"], out["BB_low"] = mid, mid + 2 * std, mid - 2 * std
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    out["MACD"] = ema12 - ema26
    out["MACD_signal"] = out["MACD"].ewm(span=9, adjust=False).mean()
    out["MACD_hist"] = out["MACD"] - out["MACD_signal"]
    out["RSI14"] = rsi(close, 14)
    low9 = out["Low"].rolling(9).min()
    high9 = out["High"].rolling(9).max()
    rsv = ((close - low9) / (high9 - low9).replace(0, np.nan) * 100).astype(float)
    out["K"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    out["D"] = out["K"].ewm(alpha=1 / 3, adjust=False).mean()
    return out


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).astype(float).fillna(100.0)


def signals(df: pd.DataFrame) -> list[tuple[str, str]]:
    """Plain-language reading of the latest bar: (tone, text) with tone in good/bad/neutral."""
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else last
    out: list[tuple[str, str]] = []
    c = last["Close"]
    for n, label in ((20, "月線"), (60, "季線"), (240, "年線")):
        v = last.get(f"SMA{n}")
        if pd.notna(v):
            above = c > v
            out.append(("good" if above else "bad",
                        f"股價{'站上' if above else '跌破'}{label}（{n} 日均線 {v:,.2f}）"))
    if pd.notna(last.get("SMA20")) and pd.notna(last.get("SMA60")):
        if last["SMA20"] > last["SMA60"] and prev["SMA20"] <= prev["SMA60"]:
            out.append(("good", "月線剛向上穿越季線（黃金交叉）"))
        elif last["SMA20"] < last["SMA60"] and prev["SMA20"] >= prev["SMA60"]:
            out.append(("bad", "月線剛向下穿越季線（死亡交叉）"))
    if pd.notna(last.get("MACD_hist")):
        if last["MACD_hist"] > 0 >= prev["MACD_hist"]:
            out.append(("good", "MACD 柱狀體翻正（動能轉強）"))
        elif last["MACD_hist"] < 0 <= prev["MACD_hist"]:
            out.append(("bad", "MACD 柱狀體翻負（動能轉弱）"))
        else:
            out.append(("good" if last["MACD_hist"] > 0 else "bad",
                        f"MACD 柱狀體為{'正' if last['MACD_hist'] > 0 else '負'}"))
    r = last.get("RSI14")
    if pd.notna(r):
        if r >= 70:
            out.append(("bad", f"RSI {r:.0f}，偏過熱"))
        elif r <= 30:
            out.append(("good", f"RSI {r:.0f}，偏超賣"))
        else:
            out.append(("neutral", f"RSI {r:.0f}，中性區間"))
    if pd.notna(last.get("BB_up")) and pd.notna(last.get("BB_low")):
        if c > last["BB_up"]:
            out.append(("bad", "收盤在布林上軌之上，短線偏離均值"))
        elif c < last["BB_low"]:
            out.append(("good", "收盤在布林下軌之下，短線超跌"))
    return out
