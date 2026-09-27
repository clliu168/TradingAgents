"""Suggest Taiwan and US stocks for a short-term and a long-term horizon, with reasons.

Two stages:
  1. Screen: rank each market's universe with deterministic rules
     (tradingagents/screener.py) and keep the top N per market and horizon.
  2. Debate: run the full TradingAgents graph on every candidate with that
     horizon; a candidate is suggested only if the Portfolio Manager rates it
     Buy or Overweight. The rest are listed with the reason they were dropped.

Examples:
    python recommend.py                         # both horizons, 3 per market
    python recommend.py --top 2 --horizon long
    python recommend.py --screen-only           # stage 1 only, no LLM cost
    python recommend.py --markets TW --portfolio my_book.json

Output: recommendations/recommendations_<date>.md
Research output only; not investment advice.
"""

from __future__ import annotations

import argparse
import re
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from run_watchlist import config_for  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402
from tradingagents.portfolio import load_portfolio  # noqa: E402
from tradingagents.screener import UNIVERSES, build_feature_table, screen  # noqa: E402

POSITIVE = {"Buy", "Overweight"}
HORIZON_LABEL = {"short": "短線（數天到數週）", "long": "中長期（6 個月以上）"}
MARKET_LABEL = {"TW": "台股", "US": "美股"}


def last_weekday(d: date) -> date:
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def decision_field(text: str, name: str) -> str:
    """One labelled section of the Portfolio Manager's rendered decision."""
    m = re.search(rf"\*\*{re.escape(name)}\*\*:\s*(.*?)(?=\n\s*\n\*\*|\Z)", text or "", re.S)
    return m.group(1).strip() if m else ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--horizon", choices=["short", "long", "both"], default="both")
    ap.add_argument("--markets", nargs="+", choices=["TW", "US"], default=["TW", "US"])
    ap.add_argument("--top", type=int, default=3, help="candidates per market and horizon sent to the debate")
    ap.add_argument("--date", default=last_weekday(date.today() - timedelta(days=1)).isoformat(),
                    help="as-of date (default: last completed weekday)")
    ap.add_argument("--language", default="Traditional Chinese")
    ap.add_argument("--portfolio", help="portfolio JSON so sizing reflects what you hold")
    ap.add_argument("--screen-only", action="store_true", help="skip the LLM debate")
    ap.add_argument("--out", default="recommendations")
    args = ap.parse_args(argv)

    horizons = ["short", "long"] if args.horizon == "both" else [args.horizon]
    universe = [t for m in args.markets for t in UNIVERSES[m]]
    portfolio = load_portfolio(args.portfolio) if args.portfolio else None
    base_dir = Path.home() / ".tradingagents"

    print(f"Screening {len(universe)} symbols as of {args.date} ...", flush=True)
    table = build_feature_table(universe, args.date)
    print(f"{len(table)} symbols have enough history and liquidity.", flush=True)

    lines = [
        f"# 選股建議：{args.date}",
        "",
        "由 TradingAgents 產生的研究參考，不構成投資建議。"
        "第一階段依量化規則從股票池篩出候選股；第二階段由多個 agent 辯論，"
        "只有最終評等為 Buy 或 Overweight 的才列入建議。",
        "",
    ]
    exit_code = 0
    for horizon in horizons:
        candidates = screen(table, horizon, top_n=args.top, markets=args.markets)
        suggested, dropped = [], []
        for c in candidates:
            print(f"\n=== {c.ticker} ({c.name}) | {horizon} | screen #{c.rank} ===", flush=True)
            if args.screen_only:
                suggested.append((c, None, ""))
                continue
            try:
                graph = TradingAgentsGraph(config=config_for(c.ticker, horizon, args.language, base_dir))
                state, rating = graph.propagate(c.ticker, args.date, portfolio=portfolio)
                graph.save_reports(state, c.ticker)
                decision = state.get("final_trade_decision", "")
                (suggested if rating in POSITIVE else dropped).append((c, rating, decision))
            except Exception as exc:  # keep going through the list
                traceback.print_exc()
                dropped.append((c, f"ERROR: {exc}", ""))
                exit_code = 1

        lines += [f"## {HORIZON_LABEL[horizon]}", ""]
        if not suggested:
            lines += ["這次沒有候選股通過多空辯論。", ""]
        else:
            lines += ["| 市場 | 代碼 | 名稱 | 評等 | 目標價 | 持有期間 |", "| --- | --- | --- | --- | --- | --- |"]
            for c, rating, dec in suggested:
                lines.append(f"| {MARKET_LABEL[c.market]} | {c.ticker} | {c.name} | {rating or '（僅篩選）'} "
                             f"| {decision_field(dec, 'Price Target') or '-'} | {decision_field(dec, 'Time Horizon') or '-'} |")
            lines.append("")
            for c, _rating, dec in suggested:
                lines += [f"### {c.ticker} {c.name}", "", f"**量化篩選理由**：{c.reason}", ""]
                if dec:
                    lines += [f"**行動方案**：{decision_field(dec, 'Executive Summary')}", "",
                              f"**投資論點**：{decision_field(dec, 'Investment Thesis')}", ""]
        if dropped:
            lines += ["**通過篩選但未獲建議**", ""]
            for c, rating, dec in dropped:
                why = decision_field(dec, "Executive Summary") or "執行失敗，請看終端機錯誤訊息。"
                lines.append(f"- {c.ticker} {c.name}（{rating}）：{why}")
            lines.append("")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"recommendations_{args.date}_{datetime.now():%H%M}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWritten to {path}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
