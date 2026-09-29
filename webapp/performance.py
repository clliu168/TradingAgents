"""Scorecard for past AI decisions: what happened after each call.

Every completed TradingAgents run appends its decision to a markdown decision
log (one per horizon on the server). Here each logged decision is scored
against prices that came after it: the stock's return over 5, 21 and 63
trading days from the analysis-date close, the benchmark's return over the
same window, and the difference (alpha). A call is a "hit" when the alpha has
the sign its rating implies (Buy/Overweight > 0, Sell/Underweight < 0).
Hold calls are shown but not scored.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from tradingagents.decision_log import TradingMemoryLog
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.settlement import resolve_benchmark

WINDOWS = (5, 21, 63)
DIRECTION = {"Buy": 1, "Overweight": 1, "Hold": 0, "Underweight": -1, "Sell": -1}


def memory_dir() -> Path:
    return Path.home() / ".tradingagents" / "memory"


def load_decisions(paths: list[Path] | None = None) -> pd.DataFrame:
    """All logged decisions, one row each: date, ticker, rating, horizon, decision."""
    if paths is None:
        paths = sorted(memory_dir().glob("trading_memory*.md"))
    rows = []
    for p in paths:
        stem = p.stem.replace("trading_memory", "").strip("_")
        horizon = {"short": "短線", "long": "中長期"}.get(stem, "未分類")
        for e in TradingMemoryLog({"memory_log_path": str(p)}).load_entries():
            rows.append({"date": e["date"], "ticker": e["ticker"], "rating": e["rating"],
                         "horizon": horizon, "decision": e.get("decision", "")})
    df = pd.DataFrame(rows, columns=["date", "ticker", "rating", "horizon", "decision"])
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        df = df.drop_duplicates(["date", "ticker", "horizon"]).sort_values("date", ascending=False)
    return df.reset_index(drop=True)


def forward_return(closes: pd.Series, start: pd.Timestamp, days: int) -> float | None:
    """Close-to-close return from the last bar on/before ``start`` to ``days`` bars later."""
    closes = closes.dropna().sort_index()
    before = closes[closes.index <= start]
    if before.empty:
        return None
    i = closes.index.get_loc(before.index[-1])
    if i + days >= len(closes):
        return None
    return float(closes.iloc[i + days] / closes.iloc[i] - 1)


def evaluate(decisions: pd.DataFrame, closes_fn: Callable[[str], pd.Series],
             windows: tuple[int, ...] = WINDOWS) -> pd.DataFrame:
    """Add ret_N, bench_N, alpha_N and hit_N columns for each window."""
    out = decisions.copy()
    cache: dict[str, pd.Series] = {}

    def closes(sym: str) -> pd.Series:
        if sym not in cache:
            try:
                cache[sym] = closes_fn(sym)
            except Exception:  # noqa: BLE001 — an unpriceable symbol leaves its rows unscored
                cache[sym] = pd.Series(dtype=float)
        return cache[sym]

    out["benchmark"] = [resolve_benchmark(t, DEFAULT_CONFIG) for t in out["ticker"]]
    out["direction"] = [DIRECTION.get(r, 0) for r in out["rating"]]
    for n in windows:
        rets, benches = [], []
        for _, r in out.iterrows():
            rets.append(forward_return(closes(r["ticker"]), r["date"], n))
            benches.append(forward_return(closes(r["benchmark"]), r["date"], n))
        out[f"ret_{n}"] = pd.array(rets, dtype="Float64")
        out[f"bench_{n}"] = pd.array(benches, dtype="Float64")
        out[f"alpha_{n}"] = out[f"ret_{n}"] - out[f"bench_{n}"]
        scored = out[f"alpha_{n}"].notna() & (out["direction"] != 0)
        hit = np.sign(out[f"alpha_{n}"].astype(float).fillna(0)) == out["direction"]
        out[f"hit_{n}"] = pd.array([bool(h) if s else None for h, s in zip(hit, scored, strict=False)],
                                   dtype="boolean")
    return out


def summarize(scored: pd.DataFrame, window: int, by: str | None = None) -> pd.DataFrame:
    """Count, hit rate and mean alpha (direction-adjusted) of directional calls."""
    d = scored[(scored["direction"] != 0) & scored[f"alpha_{window}"].notna()].copy()
    if d.empty:
        return pd.DataFrame(columns=["組別", "已評估筆數", "勝率", "平均超額報酬（依方向）", "平均個股報酬"])
    d["signed_alpha"] = d[f"alpha_{window}"].astype(float) * d["direction"]
    groups = [("全部", d)] if by is None else list(d.groupby(by))
    rows = [{
        "組別": name,
        "已評估筆數": len(g),
        "勝率": float(g[f"hit_{window}"].astype(float).mean()),
        "平均超額報酬（依方向）": float(g["signed_alpha"].mean()),
        "平均個股報酬": float(g[f"ret_{window}"].astype(float).mean()),
    } for name, g in groups]
    return pd.DataFrame(rows)
