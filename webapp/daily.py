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


def prefetch_news(per_topic: int) -> None:
    from webapp import articles, data
    from webapp.ui import load_watchlist

    todo = []
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
    code = 0
    if args.top > 0:
        code = run_recommend(
            ["--horizon", "both", "--markets", *args.markets, "--top", str(args.top)],
            f"每日自動選股 短線 + 中長期・{'/'.join(args.markets)}・前 {args.top} 檔",
        )
    if args.news > 0:
        try:
            prefetch_news(args.news)
        except Exception as exc:  # noqa: BLE001
            print(f"news prefetch failed: {exc}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
