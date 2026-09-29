"""Your actual holdings: storage, valuation in TWD, rebalancing, and the
portfolio context handed to the AI runs."""

from __future__ import annotations

import json
import math
from collections.abc import Callable

import pandas as pd

from webapp.jobs import DATA_DIR

PORTFOLIO_FILE = DATA_DIR / "portfolio.json"
CONTEXT_FILE = DATA_DIR / "portfolio_context.json"
EMPTY = {"cash_twd": 0.0, "cash_usd": 0.0, "rebalance_band": 0.05, "positions": []}


def currency_of(ticker: str) -> str:
    t = ticker.upper()
    return "TWD" if t.endswith(".TW") or t.endswith(".TWO") else "USD"


def load() -> dict:
    try:
        data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
        return {**EMPTY, **data}
    except (OSError, ValueError):
        return dict(EMPTY, positions=[])


def save(pf: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_FILE.write_text(json.dumps(pf, ensure_ascii=False, indent=1), encoding="utf-8")
    write_context(pf)


def _num(x, default=0.0) -> float:
    try:
        v = float(x)
        return default if math.isnan(v) else v
    except (TypeError, ValueError):
        return default


def valuate(pf: dict, price_fn: Callable[[str], float | None], usd_twd: float) -> pd.DataFrame:
    """One row per position (plus cash rows) with value in TWD, P&L, weight and target gap."""
    rows = []
    for p in pf.get("positions", []):
        t = str(p.get("ticker", "")).strip().upper()
        if not t:
            continue
        shares, cost = _num(p.get("shares")), _num(p.get("cost"))
        cur = currency_of(t)
        fx = usd_twd if cur == "USD" else 1.0
        price = price_fn(t)
        value_local = shares * price if price is not None else None
        rows.append({
            "代碼": t, "幣別": cur, "股數": shares, "成本價": cost, "現價": price,
            "市值（原幣）": value_local,
            "市值（台幣）": value_local * fx if value_local is not None else None,
            "損益（原幣）": (price - cost) * shares if price is not None and cost else None,
            "報酬率": (price / cost - 1) if price is not None and cost else None,
            "目標比例": _num(p.get("target")) / 100.0,
        })
    for cur, key, fx in (("TWD", "cash_twd", 1.0), ("USD", "cash_usd", usd_twd)):
        amt = _num(pf.get(key))
        if amt:
            nan = float("nan")
            rows.append({"代碼": f"現金 {cur}", "幣別": cur, "股數": nan, "成本價": nan, "現價": nan,
                         "市值（原幣）": amt, "市值（台幣）": amt * fx, "損益（原幣）": nan,
                         "報酬率": nan, "目標比例": nan})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    total = df["市值（台幣）"].fillna(0).sum()
    df["目前比例"] = df["市值（台幣）"] / total if total else None
    df["偏離"] = df["目前比例"] - df["目標比例"]
    return df


def rebalance(df: pd.DataFrame, band: float, usd_twd: float) -> pd.DataFrame:
    """Positions outside ±band of target, with the trade that brings each back to target."""
    if df.empty:
        return df
    total = df["市值（台幣）"].fillna(0).sum()
    d = df[df["目標比例"].notna() & (df["目標比例"] > 0) & df["偏離"].notna()]
    d = d[d["偏離"].abs() > band].copy()
    if d.empty:
        return d
    d["調整金額（台幣）"] = -d["偏離"] * total
    fx = d["幣別"].map({"USD": usd_twd, "TWD": 1.0})
    d["約需買賣股數"] = (d["調整金額（台幣）"] / fx / d["現價"]).abs().round(0)
    d["動作"] = ["買進" if x > 0 else "賣出" for x in d["調整金額（台幣）"]]
    return d[["代碼", "目前比例", "目標比例", "偏離", "動作", "調整金額（台幣）", "約需買賣股數"]]


def write_context(pf: dict) -> None:
    """Holdings in TradingAgents' PortfolioContext format, for --portfolio."""
    ctx = {
        "cash": _num(pf.get("cash_twd")) + 0.0,
        "currency": f"TWD (plus USD cash {_num(pf.get('cash_usd')):.0f})" if _num(pf.get("cash_usd")) else "TWD",
        "positions": [{"ticker": str(p["ticker"]).strip().upper(), "quantity": _num(p.get("shares")),
                       "average_price": _num(p.get("cost")) or None}
                      for p in pf.get("positions", []) if str(p.get("ticker", "")).strip()],
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONTEXT_FILE.write_text(json.dumps(ctx, ensure_ascii=False, indent=1), encoding="utf-8")


def context_path_if_any() -> str | None:
    pf = load()
    if not pf.get("positions"):
        return None
    write_context(pf)
    return str(CONTEXT_FILE)
