"""Run TradingAgents over a watchlist of Taiwan and US stocks, for one or both
investment horizons, and collect the final decisions into one summary file.

Examples:
    python run_watchlist.py 2330.TW 2454.TW NVDA --horizon both
    python run_watchlist.py NVDA AAPL --horizon long --date 2026-09-25
    python run_watchlist.py 2330.TW --portfolio my_book.json --language "Traditional Chinese"

Provider, models and keys come from .env (TRADINGAGENTS_LLM_PROVIDER,
TRADINGAGENTS_DEEP_THINK_LLM, TRADINGAGENTS_QUICK_THINK_LLM, *_API_KEY).
Each horizon keeps its own decision log, so a long-term thesis is never
reflected on with a short-term outcome window.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from tradingagents.default_config import DEFAULT_CONFIG  # noqa: E402
from tradingagents.graph.trading_graph import TradingAgentsGraph  # noqa: E402
from tradingagents.portfolio import load_portfolio  # noqa: E402
from webapp.usage import UsageRecorder, over_budget  # noqa: E402

# Macro headlines the global-news tool searches in addition to the defaults
# when the ticker trades in Taiwan; the defaults are all US/EU centric.
TAIWAN_NEWS_QUERIES = [
    "Taiwan stock market TAIEX",
    "Taiwan central bank interest rate New Taiwan dollar",
    "Taiwan exports semiconductor TSMC supply chain",
    "cross-strait tensions Taiwan geopolitics",
]


def is_taiwan(ticker: str) -> bool:
    t = ticker.strip().upper()
    return t.endswith(".TW") or t.endswith(".TWO")


def config_for(ticker: str, horizon: str, language: str, base_dir: Path) -> dict:
    config = deepcopy(DEFAULT_CONFIG)
    config["investment_horizon"] = horizon
    config["output_language"] = language
    config["memory_log_path"] = str(base_dir / "memory" / f"trading_memory_{horizon}.md")
    if is_taiwan(ticker):
        config["global_news_queries"] = TAIWAN_NEWS_QUERIES + list(config["global_news_queries"])
        # FRED is US macro only; keep it as context but do not fail without a key.
    if horizon == "long":
        # A longer thesis deserves a longer look back at macro news.
        config["global_news_lookback_days"] = max(config["global_news_lookback_days"], 30)
    return config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("tickers", nargs="+", help="e.g. 2330.TW 6488.TWO NVDA")
    parser.add_argument("--horizon", choices=["short", "long", "both"], default="both")
    parser.add_argument("--date", default=date.today().isoformat(), help="analysis date YYYY-MM-DD")
    parser.add_argument("--language", default=os.getenv("TRADINGAGENTS_OUTPUT_LANGUAGE", "Traditional Chinese"))
    parser.add_argument("--portfolio", help="portfolio JSON (see README 'Current holdings')")
    parser.add_argument("--out", default="watchlist_results", help="summary output directory")
    args = parser.parse_args(argv)

    horizons = ["short", "long"] if args.horizon == "both" else [args.horizon]
    portfolio = load_portfolio(args.portfolio) if args.portfolio else None
    base_dir = Path(os.getenv("TRADINGAGENTS_HOME", Path.home() / ".tradingagents"))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows, sections = [], []
    for horizon in horizons:
        for raw in args.tickers:
            ticker = raw.strip().upper()
            print(f"\n=== {ticker} | {horizon} | {args.date} ===", flush=True)
            try:
                blocked, why = over_budget()
                if blocked:
                    print(f"Budget reached, skipping {ticker}: {why}", flush=True)
                    rows.append((ticker, horizon, f"SKIPPED: {why}"))
                    continue
                graph = TradingAgentsGraph(config=config_for(ticker, horizon, args.language, base_dir),
                                           callbacks=[UsageRecorder(f"watchlist:{ticker}:{horizon}")])
                state, signal = graph.propagate(ticker, args.date, portfolio=portfolio)
                graph.save_reports(state, ticker)
                rows.append((ticker, horizon, signal))
                sections.append(f"## {ticker} · {horizon}\n\n**Rating: {signal}**\n\n{state.get('final_trade_decision', '')}")
            except Exception as exc:  # keep going through the list
                traceback.print_exc()
                rows.append((ticker, horizon, f"ERROR: {exc}"))

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    summary = out_dir / f"summary_{args.date}_{stamp}.md"
    table = "\n".join(f"| {t} | {h} | {s} |" for t, h, s in rows)
    summary.write_text(
        f"# Watchlist decisions, {args.date}\n\n"
        "Research output of TradingAgents; not investment advice.\n\n"
        f"| Ticker | Horizon | Rating |\n| --- | --- | --- |\n{table}\n\n" + "\n\n".join(sections),
        encoding="utf-8",
    )
    print(f"\nSummary written to {summary}")
    return 0 if all(not str(s).startswith("ERROR") for _, _, s in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
