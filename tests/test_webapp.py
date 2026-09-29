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


@pytest.mark.parametrize("page", ["views/overview.py", "views/stock.py", "views/news.py",
                                  "views/generate.py", "views/reports.py"])
def test_page_renders(page, monkeypatch, tmp_path):
    monkeypatch.setattr(data, "DEMO", True)
    monkeypatch.setattr(services, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
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
