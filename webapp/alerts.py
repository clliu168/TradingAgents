"""Watchlist and holdings alerts, sent through webapp.notify.

    python -m webapp.alerts            # check now and notify (used by the timer)
    python -m webapp.alerts --dry-run  # print what would be sent

Rules live in webapp_data/alerts.json and are edited on the 設定與費用 page.
Each alert fires at most once per ticker, rule and bar date.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable

import pandas as pd

from tradingagents.dataflows.tw_names import label as tw_label
from webapp.indicators import add_indicators
from webapp.jobs import DATA_DIR

RULES_FILE = DATA_DIR / "alerts.json"
SENT_FILE = DATA_DIR / "alerts_sent.json"
DEFAULT_RULES = {
    "enabled": True,
    "sma60_cross": True,        # close crosses the 60-day average
    "sma240_cross": True,       # close crosses the 240-day average
    "rsi_high": 75,             # RSI(14) at or above (0 = off)
    "rsi_low": 25,              # RSI(14) at or below (0 = off)
    "daily_move_pct": 5.0,      # |daily change| at or above, in % (0 = off)
    "rebalance": True,          # holdings outside their target band
    "price_targets": [],        # [{"ticker": "2330.TW", "above": 1300, "below": 1000}]
}


def load_rules() -> dict:
    try:
        return {**DEFAULT_RULES, **json.loads(RULES_FILE.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULT_RULES)


def save_rules(rules: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RULES_FILE.write_text(json.dumps(rules, ensure_ascii=False, indent=1), encoding="utf-8")


def check_ticker(ticker: str, hist: pd.DataFrame, rules: dict) -> list[tuple[str, str]]:
    """(rule key, message) pairs triggered by the latest bar of ``hist``."""
    if hist is None or len(hist) < 3:
        return []
    ind = add_indicators(hist)
    last, prev = ind.iloc[-1], ind.iloc[-2]
    c, pc = float(last["Close"]), float(prev["Close"])
    who = tw_label(ticker)  # "2330.TW 台積電"
    out = []
    for n, label, key in ((60, "季線", "sma60_cross"), (240, "年線", "sma240_cross")):
        col = f"SMA{n}"
        if rules.get(key) and pd.notna(last.get(col)) and pd.notna(prev.get(col)):
            if pc >= prev[col] and c < last[col]:
                out.append((f"{key}_down", f"📉 {who} 跌破{label}（{last[col]:,.2f}），收 {c:,.2f}"))
            elif pc <= prev[col] and c > last[col]:
                out.append((f"{key}_up", f"📈 {who} 站上{label}（{last[col]:,.2f}），收 {c:,.2f}"))
    r = last.get("RSI14")
    if pd.notna(r):
        if rules.get("rsi_high") and r >= rules["rsi_high"]:
            out.append(("rsi_high", f"🔥 {who} RSI {r:.0f}，偏過熱"))
        if rules.get("rsi_low") and r <= rules["rsi_low"]:
            out.append(("rsi_low", f"🧊 {who} RSI {r:.0f}，偏超賣"))
    move = c / pc - 1
    if rules.get("daily_move_pct") and abs(move) * 100 >= rules["daily_move_pct"]:
        out.append(("move", f"{'🚀' if move > 0 else '⚠️'} {who} 單日 {move:+.2%}，收 {c:,.2f}"))
    for t in rules.get("price_targets", []):
        if str(t.get("ticker", "")).upper() != ticker:
            continue
        if t.get("above") and c >= float(t["above"]) > pc:
            out.append(("above", f"🎯 {who} 漲到 {c:,.2f}，超過設定的 {float(t['above']):,.2f}"))
        if t.get("below") and c <= float(t["below"]) < pc:
            out.append(("below", f"🎯 {who} 跌到 {c:,.2f}，低於設定的 {float(t['below']):,.2f}"))
    return out


def _sent() -> dict:
    try:
        return json.loads(SENT_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def run(history_fn: Callable[[str], pd.DataFrame], tickers: list[str], dry_run: bool = False,
        rebalance_lines: list[str] | None = None) -> list[str]:
    """Check every ticker, drop alerts already sent for the same bar, notify the rest."""
    rules = load_rules()
    if not rules.get("enabled"):
        return []
    sent = _sent()
    fresh, keys = [], []
    for t in tickers:
        try:
            hist = history_fn(t)
        except Exception:  # noqa: BLE001
            continue
        if hist is None or hist.empty:
            continue
        bar = f"{hist.index[-1]:%Y-%m-%d}"
        for rule, msg in check_ticker(t, hist, rules):
            k = f"{t}|{rule}|{bar}"
            if k not in sent:
                fresh.append(f"{msg}（{bar}）")
                keys.append(k)
    if rules.get("rebalance") and rebalance_lines:
        k = f"rebalance|{pd.Timestamp.today():%Y-%m-%d}"
        if k not in sent:
            fresh.append("⚖️ 持股偏離目標比例：\n" + "\n".join(rebalance_lines))
            keys.append(k)
    if fresh and not dry_run:
        from webapp import notify

        notify.send("🔔 TradingAgents 警示\n\n" + "\n".join(fresh), subject="TradingAgents 警示")
        cutoff = f"{pd.Timestamp.today() - pd.Timedelta(days=30):%Y-%m-%d}"
        kept = {k: v for k, v in sent.items() if v >= cutoff}
        kept.update({k: f"{pd.Timestamp.today():%Y-%m-%d}" for k in keys})
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        SENT_FILE.write_text(json.dumps(kept, indent=0), encoding="utf-8")
    return fresh


def _rebalance_lines() -> list[str]:
    from webapp import data, portfolio as pfm

    pf = pfm.load()
    if not pf.get("positions"):
        return []
    fx = data.history("TWD=X", 10, warmup=0)
    usd_twd = float(fx["Close"].iloc[-1]) if not fx.empty else 32.0

    def price(t):
        h = data.history(t, 10, warmup=0)
        return float(h["Close"].iloc[-1]) if not h.empty else None

    rb = pfm.rebalance(pfm.valuate(pf, price, usd_twd), pf["rebalance_band"], usd_twd)
    return [f"{tw_label(r['代碼'])} 目前 {r['目前比例']:.1%}／目標 {r['目標比例']:.1%}，建議{r['動作']}約 "
            f"{abs(r['調整金額（台幣）']):,.0f} 台幣" for _, r in rb.iterrows()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    from webapp import data, portfolio as pfm
    from webapp.ui import load_watchlist

    tickers = list(dict.fromkeys(load_watchlist() + [p["ticker"] for p in pfm.load().get("positions", [])]))
    fired = run(lambda t: data.history(t, 400), tickers, dry_run=args.dry_run,
                rebalance_lines=_rebalance_lines())
    print("\n".join(fired) if fired else "no new alerts", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
