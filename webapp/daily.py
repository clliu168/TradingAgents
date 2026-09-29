"""Daily update, run by the systemd timer on the server (or by hand):

    python -m webapp.daily --top 5

1. AI stock picks (recommend.py) for both horizons and markets. The run is
   recorded like a web job, so it shows up on the 「產生報告」 page with its log.
2. Pre-summarize the market and watchlist news, so the 新聞 page opens with
   summaries already in place.

Exit code is non-zero if the picks failed; news failures are logged only.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

from webapp.jobs import JOBS_DIR, ROOT


def run_recommend(args: list[str], label: str) -> int:
    job_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + "daily"
    jdir = JOBS_DIR / job_id
    jdir.mkdir(parents=True)
    cmd = [sys.executable, "-u", str(ROOT / "recommend.py"), *args]
    meta = {"id": job_id, "kind": "recommend", "label": label, "cmd": cmd,
            "started": datetime.now().isoformat(), "pid": os.getpid()}
    (jdir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    with open(jdir / "log.txt", "w", encoding="utf-8") as log:
        code = subprocess.call(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    (jdir / "exit_code").write_text(str(code))
    print(f"recommend exit code {code}; log: {jdir / 'log.txt'}", flush=True)
    return code


def notify_picks(job_dir_code: int) -> None:
    """Send today's suggestions (or the failure) to the configured channels."""
    from webapp import jobs, notify
    from webapp.services import parse_recommendations

    latest = jobs.list_jobs()[0] if jobs.list_jobs() else None
    out = jobs.output_file(latest["dir"]) if latest else None
    if job_dir_code != 0 or not out or not out.exists():
        notify.send("⚠️ TradingAgents 每日選股失敗，請到網頁「產生報告」頁看紀錄。")
        return
    rows = parse_recommendations(out.read_text(encoding="utf-8"))
    if not rows:
        notify.send(f"📋 TradingAgents 每日選股完成（{out.stem}）：今天沒有候選股通過多空辯論。")
        return
    lines = [f"・[{r['期間'].split('（')[0]}] {r['市場']} {r['代碼']} {r['名稱']}：{r['評等']}"
             + (f"，目標價 {r['目標價']}" if r["目標價"] not in ("", "-") else "") for r in rows]
    notify.send(f"📋 TradingAgents 每日選股（{out.stem.replace('recommendations_', '')}）\n\n"
                + "\n".join(lines) + "\n\n詳細理由請看網頁「報告與建議」頁。僅供研究參考，不構成投資建議。",
                subject="TradingAgents 每日選股")


def prefetch_news(per_topic: int) -> None:
    from webapp import articles, cnnews, data
    from webapp.ui import load_watchlist

    todo = list(cnnews.yahoo_tw("台股")[:per_topic]) + list(cnnews.yahoo_tw("國際財經")[:per_topic // 2])
    for topic in data.MARKET_NEWS_QUERIES:
        todo += data.market_news(topic)[:per_topic]
    for t in load_watchlist():
        todo += data.ticker_news(t)[:5]
    seen, unique = set(), []
    for a in todo:
        k = a.get("link") or a["title"]
        if k not in seen and not articles.cached(k):
            seen.add(k)
            unique.append(a)
    print(f"summarizing {len(unique)} new articles", flush=True)
    if not unique:
        return
    llm = articles._llm()
    ok = 0
    for a in unique:
        try:
            articles.summarize(a, llm=llm)
            ok += 1
        except Exception as exc:  # noqa: BLE001 — one bad article must not stop the rest
            print(f"  skip: {a['title'][:60]} ({exc})", flush=True)
    print(f"summarized {ok}/{len(unique)}", flush=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--top", type=int, default=5, help="candidates per market and horizon (0 = skip AI picks)")
    ap.add_argument("--markets", nargs="+", default=["TW", "US"])
    ap.add_argument("--news", type=int, default=15, help="articles per market tab to pre-summarize (0 = skip)")
    args = ap.parse_args(argv)

    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    from webapp.usage import over_budget

    code = 0
    blocked, why = over_budget()
    if blocked:
        print(f"Budget reached, skipping AI picks and news summaries: {why}", flush=True)
        from webapp import notify

        notify.send(f"⚠️ TradingAgents 每日更新已暫停：{why}。可在網頁「設定與費用」頁調整上限。")
        return 0
    if args.top > 0:
        from webapp import portfolio as pfm

        ctx = pfm.context_path_if_any()
        code = run_recommend(
            ["--horizon", "both", "--markets", *args.markets, "--top", str(args.top),
             *(["--portfolio", ctx] if ctx else [])],
            f"每日自動選股 短線 + 中長期・{'/'.join(args.markets)}・前 {args.top} 檔",
        )
        try:
            notify_picks(code)
        except Exception as exc:  # noqa: BLE001
            print(f"notify failed: {exc}", flush=True)
    if args.news > 0:
        try:
            prefetch_news(args.news)
        except Exception as exc:  # noqa: BLE001
            print(f"news prefetch failed: {exc}", flush=True)
    try:
        from webapp import alerts

        alerts.main([])
    except Exception as exc:  # noqa: BLE001
        print(f"alerts failed: {exc}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
