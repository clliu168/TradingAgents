"""Web app: pure helpers, and every page renders in demo mode without errors."""

import os

import pytest

pytest.importorskip("streamlit")
pytest.importorskip("plotly")
os.environ["TA_WEB_DEMO"] = "1"

from streamlit.testing.v1 import AppTest  # noqa: E402

from webapp import data, jobs, services  # noqa: E402
from webapp.indicators import add_indicators, signals  # noqa: E402
from webapp.ui import normalize_ticker  # noqa: E402

REC = """# 選股建議：2026-09-25

## 短線（數天到數週）

| 市場 | 代碼 | 名稱 | 評等 | 目標價 | 持有期間 |
| --- | --- | --- | --- | --- | --- |
| 台股 | 2454.TW | MediaTek | Buy | 1650 | 2-4 weeks |

### 2454.TW MediaTek

**量化篩選理由**：理由。

## 中長期（6 個月以上）

| 市場 | 代碼 | 名稱 | 評等 | 目標價 | 持有期間 |
| --- | --- | --- | --- | --- | --- |
| 美股 | NVDA | NVIDIA | Overweight | - | 12 months |

### NVDA NVIDIA

**行動方案**：分批。
"""


def test_parse_recommendations():
    rows = services.parse_recommendations(REC)
    assert [(r["代碼"], r["評等"], r["期間"][:2]) for r in rows] == [("2454.TW", "Buy", "短線"),
                                                                    ("NVDA", "Overweight", "中長")]
    sections = services.split_report_sections(REC)
    assert "理由" in sections["2454.TW"] and "分批" in sections["NVDA"]


@pytest.mark.parametrize("raw, want", [("2330", "2330.TW"), ("0050", "0050.TW"), ("006208", "006208.TW"),
                                       ("00878", "00878.TW"), (" nvda ", "NVDA"), ("6488.two", "6488.TWO")])
def test_normalize_ticker(raw, want):
    assert normalize_ticker(raw) == want


def test_indicators_and_signals():
    df = add_indicators(data._demo_history("2330.TW", 365))
    last = df.iloc[-1]
    assert 0 <= last["RSI14"] <= 100 and 0 <= last["K"] <= 100
    assert df["SMA240"].notna().iloc[-1]
    assert signals(df) and all(tone in ("good", "bad", "neutral") for tone, _ in signals(df))


def test_job_output_file(tmp_path):
    (tmp_path / "log.txt").write_text("x\nWritten to recommendations/r.md\n", encoding="utf-8")
    assert jobs.output_file(tmp_path) == jobs.ROOT / "recommendations/r.md"


PAGES = ["views/overview.py", "views/stock.py", "views/compare.py", "views/news.py", "views/calendar.py",
         "views/generate.py", "views/reports.py", "views/performance.py", "views/holdings.py", "views/settings.py"]


def _isolate(monkeypatch, tmp_path):
    from webapp import alerts, calendar_data, performance, portfolio, usage

    monkeypatch.setattr(data, "DEMO", True)
    monkeypatch.setattr(services, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    for mod, attr in ((portfolio, "PORTFOLIO_FILE"), (portfolio, "CONTEXT_FILE"), (usage, "USAGE_FILE"),
                      (usage, "PRICING_FILE"), (usage, "BUDGET_FILE"), (alerts, "RULES_FILE"),
                      (alerts, "SENT_FILE"), (calendar_data, "MACRO_FILE")):
        monkeypatch.setattr(mod, attr, tmp_path / f"{mod.__name__}_{attr}.json")
    mem = tmp_path / "memory"
    mem.mkdir()
    (mem / "trading_memory_short.md").write_text(
        "[2025-06-02 | 2330.TW | Buy | pending]\n\nDECISION:\n**Rating**: Buy\n\n<!-- ENTRY_END -->\n\n"
        "[2025-06-02 | NVDA | Hold | pending]\n\nDECISION:\n**Rating**: Hold\n\n<!-- ENTRY_END -->\n\n",
        encoding="utf-8")
    monkeypatch.setattr(performance, "memory_dir", lambda: mem)
    portfolio.save({"cash_twd": 100000, "cash_usd": 1000, "rebalance_band": 0.05,
                    "positions": [{"ticker": "006208.TW", "shares": 1000, "cost": 100, "target": 60},
                                  {"ticker": "VTI", "shares": 50, "cost": 250, "target": 30}]})
    usage.record("recommend:2330.TW:short", "gpt-6-sol", 10000, 2000)


@pytest.mark.parametrize("page", PAGES)
def test_page_renders(page, monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    at = AppTest.from_file(str(jobs.ROOT / "webapp" / "app.py"), default_timeout=60)
    at.run()
    if page != "views/overview.py":
        at.switch_page(page)
        at.run()
    assert not at.exception, at.exception


def test_extract_text_keeps_article_paragraphs():
    from webapp.articles import extract_text

    html = ("<html><body><nav><p>" + "menu link " * 10 + "</p></nav><article>"
            "<p>" + "TSMC raised its revenue outlook for the year on strong AI demand. " * 2 + "</p>"
            "<p>short</p><script>var x = 1;</script></article><footer><p>" + "copyright " * 10 + "</p></footer>"
            "</body></html>")
    text = extract_text(html)
    assert "TSMC raised" in text and "menu" not in text and "copyright" not in text and "short" not in text


def test_parse_json_from_model_reply():
    from webapp.articles import _parse_json

    reply = 'Sure:\n```json\n{"summary": "摘要", "points": ["a", "b"], "tickers": ["2330.TW"], ' \
            '"impact": "x", "sentiment": "中性"}\n```'
    data_ = _parse_json(reply)
    assert data_["summary"] == "摘要" and data_["points"] == ["a", "b"]


def test_summary_is_cached(monkeypatch, tmp_path):
    from webapp import articles

    monkeypatch.setattr(articles, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(data, "DEMO", False)
    monkeypatch.setattr(articles, "fetch_text", lambda link: "body " * 100)
    calls = []

    class FakeLLM:
        def invoke(self, prompt):
            calls.append(prompt)
            return type("R", (), {"content": '{"summary": "s", "points": ["p"], "sentiment": "偏多"}'})()

    a = {"title": "T", "link": "https://x/1", "publisher": "P"}
    assert articles.summarize(a, llm=FakeLLM())["source"] == "全文"
    assert articles.summarize(a, llm=FakeLLM())["summary"] == "s"
    assert len(calls) == 1


def test_daily_records_job_and_prefetches(monkeypatch, tmp_path):
    import subprocess

    from webapp import articles, daily

    monkeypatch.setattr(daily, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(articles, "CACHE_DIR", tmp_path / "sum")
    monkeypatch.setattr(data, "DEMO", True)
    seen = {}

    def fake_call(cmd, cwd, stdout, stderr):
        seen["cmd"] = cmd
        stdout.write("Written to recommendations/recommendations_x.md\n")
        return 0

    monkeypatch.setattr(subprocess, "call", fake_call)
    assert daily.main(["--top", "5", "--news", "2"]) == 0
    assert seen["cmd"][-6:] == ["--horizon", "both", "--markets", "TW", "US", "--top", "5"][-6:]
    listed = jobs.list_jobs()
    assert len(listed) == 1 and listed[0]["status"] == "完成" and "每日自動選股" in listed[0]["label"]
    assert any((tmp_path / "sum").glob("*.json"))


def test_performance_scoring():
    import pandas as pd

    from webapp.performance import evaluate, forward_return, summarize

    idx = pd.bdate_range("2026-01-01", periods=100)
    up = pd.Series(range(100, 200), index=idx, dtype=float)
    flat = pd.Series(100.0, index=idx)
    assert forward_return(up, idx[10], 5) == pytest.approx(up.iloc[15] / up.iloc[10] - 1)
    assert forward_return(up, idx[98], 5) is None
    dec = pd.DataFrame({"date": [idx[10], idx[10], idx[10]], "ticker": ["AAA", "AAA", "AAA"],
                        "rating": ["Buy", "Sell", "Hold"], "horizon": ["短線"] * 3, "decision": [""] * 3})
    scored = evaluate(dec, lambda s: flat if s == "SPY" else up, windows=(5,))
    assert scored["hit_5"].tolist()[:2] == [True, False] and pd.isna(scored["hit_5"].iloc[2])
    summary = summarize(scored, 5).iloc[0]
    assert summary["已評估筆數"] == 2 and summary["勝率"] == 0.5


def test_portfolio_valuation_and_rebalance():
    from webapp import portfolio as pfm

    pf = {"cash_twd": 0, "cash_usd": 0, "rebalance_band": 0.05,
          "positions": [{"ticker": "006208.TW", "shares": 1000, "cost": 100, "target": 50},
                        {"ticker": "VTI", "shares": 10, "cost": 200, "target": 50}]}
    prices = {"006208.TW": 150.0, "VTI": 300.0}
    df = pfm.valuate(pf, prices.get, usd_twd=30.0)
    # 150,000 TWD vs 10 * 300 * 30 = 90,000 TWD
    assert df.set_index("代碼")["市值（台幣）"].to_dict() == {"006208.TW": 150000.0, "VTI": 90000.0}
    rb = pfm.rebalance(df, 0.05, 30.0).set_index("代碼")
    assert rb.loc["006208.TW", "動作"] == "賣出" and rb.loc["VTI", "動作"] == "買進"
    assert rb.loc["VTI", "約需買賣股數"] == pytest.approx(30000 / 30 / 300, abs=1)


def test_usage_cost_and_budget(monkeypatch, tmp_path):
    from webapp import usage

    for attr in ("USAGE_FILE", "PRICING_FILE", "BUDGET_FILE"):
        monkeypatch.setattr(usage, attr, tmp_path / f"{attr}.json")
    usage.record("x", "gpt-6-sol-2026-08-01", 1_000_000, 100_000, cached=500_000)
    df = usage.load()
    # 500k fresh * $2 + 500k cached * $0.2 + 100k out * $10 = 1.0 + 0.1 + 1.0
    assert df["cost_usd"].iloc[0] == pytest.approx(2.1)
    usage.save_budget({"daily_usd": 2.0, "monthly_usd": 0})
    assert usage.over_budget()[0] is True
    usage.save_budget({"daily_usd": 0, "monthly_usd": 0})
    assert usage.over_budget()[0] is False


def test_usage_recorder_reads_usage_metadata(monkeypatch, tmp_path):
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    from webapp import usage

    path = tmp_path / "u.jsonl"
    rec = usage.UsageRecorder("t", path)
    rec.on_chat_model_start({}, [], run_id="r1", invocation_params={"model": "gpt-6-luna"})
    msg = AIMessage("x", usage_metadata={"input_tokens": 12, "output_tokens": 3, "total_tokens": 15})
    rec.on_llm_end(LLMResult(generations=[[ChatGeneration(message=msg)]]), run_id="r1")
    df = usage.load(path)
    assert (df["model"].iloc[0], int(df["input"].iloc[0]), int(df["output"].iloc[0])) == ("gpt-6-luna", 12, 3)


def test_alert_rules_fire_once(monkeypatch, tmp_path):
    import numpy as np
    import pandas as pd

    from webapp import alerts

    monkeypatch.setattr(alerts, "RULES_FILE", tmp_path / "r.json")
    monkeypatch.setattr(alerts, "SENT_FILE", tmp_path / "s.json")
    idx = pd.bdate_range("2025-01-01", periods=300)
    close = np.full(300, 100.0)
    close[-1] = 90.0  # -10% day, and a drop through the 60/240-day averages
    hist = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1}, index=idx)
    sent = []
    monkeypatch.setattr("webapp.notify.send", lambda text, subject="": sent.append(text) or ["telegram"])
    first = alerts.run(lambda t: hist, ["AAA"])
    assert any("單日" in m for m in first) and any("跌破季線" in m for m in first)
    assert alerts.run(lambda t: hist, ["AAA"]) == []  # same bar: nothing new
    assert len(sent) == 1


def test_parse_rss_google_and_yahoo():
    from webapp.cnnews import parse_rss

    xml = """<rss><channel>
      <item><title>台積電法說會 - 經濟日報</title><link>https://n/1</link>
        <pubDate>Mon, 28 Sep 2026 03:00:00 GMT</pubDate><source url="x">經濟日報</source>
        <description>&lt;a&gt;台積電法說會 - 經濟日報&lt;/a&gt;</description></item>
      <item><title>加權指數收高</title><link>https://y/2</link>
        <pubDate>Mon, 28 Sep 2026 06:00:00 +0800</pubDate><description>&lt;p&gt;大盤上漲 100 點&lt;/p&gt;</description></item>
    </channel></rss>"""
    items = parse_rss(xml, "Yahoo股市")
    assert items[0]["title"] == "台積電法說會" and items[0]["publisher"] == "經濟日報"
    assert items[1]["publisher"] == "Yahoo股市" and items[1]["summary"] == "大盤上漲 100 點"
    assert items[1]["pub_date"].utcoffset().total_seconds() == 8 * 3600


def test_finmind_tables():
    import pandas as pd

    from tradingagents.dataflows.vendors.finmind import net_flows, revenue_table, taiwan_stock_id

    raw = pd.DataFrame([
        {"date": "2026-09-25", "name": "Foreign_Investor", "buy": 5_000_000, "sell": 2_000_000},
        {"date": "2026-09-25", "name": "Foreign_Dealer_Self", "buy": 1_000, "sell": 0},
        {"date": "2026-09-25", "name": "Investment_Trust", "buy": 0, "sell": 500_000},
    ])
    f = net_flows(raw).iloc[0]
    assert (f["外資"], f["投信"], f["合計"]) == (3001.0, -500.0, 2501.0)
    rows = [{"date": f"{2025 + (m > 12)}-{(m - 1) % 12 + 1:02d}-10", "revenue": 100e8 * (1.2 if m > 12 else 1),
             "revenue_year": 2024 + (m > 12), "revenue_month": (m - 1) % 12 + 1} for m in range(1, 25)]
    rev = revenue_table(pd.DataFrame(rows))
    assert rev["年增率"].iloc[-1] == pytest.approx(0.2)
    assert taiwan_stock_id("6488.two") == "6488" and taiwan_stock_id("NVDA") is None


def test_taipei_time_conversion():
    from webapp.calendar_data import to_taipei

    assert f"{to_taipei('2026-10-14', '08:30'):%m/%d %H:%M}" == "10/14 20:30"  # EDT
    assert f"{to_taipei('2026-12-10', '08:30'):%m/%d %H:%M}" == "12/10 21:30"  # EST
