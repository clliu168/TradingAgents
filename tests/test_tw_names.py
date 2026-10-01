"""Chinese names for Taiwan tickers: lookup, caching, fallbacks and where they show up."""

import json
import os
import time

import pandas as pd

from tradingagents.dataflows import tw_names


def test_builtin_names_and_label():
    assert tw_names.zh_name("2330.TW") == "台積電"
    assert tw_names.zh_name("5274.two") == "信驊"
    assert tw_names.zh_name("006208.TW") == "富邦台50"
    assert tw_names.label("2454.TW") == "2454.TW 聯發科"


def test_us_and_unknown_tickers_have_no_name():
    assert tw_names.zh_name("NVDA") is None
    assert tw_names.zh_name("^TWII") is None
    assert tw_names.zh_name("9999.TW") is None
    assert tw_names.label("NVDA") == "NVDA"
    assert tw_names.label("9999.TW") == "9999.TW"


def test_downloaded_list_is_cached_and_overrides_builtin(monkeypatch):
    calls = []

    def fake_refresh():
        calls.append(1)
        names = {"9999": "測試公司", "2330": "台積電"}
        tw_names.CACHE.parent.mkdir(parents=True, exist_ok=True)
        tw_names.CACHE.write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")
        return names

    monkeypatch.setattr(tw_names, "_refresh", fake_refresh)
    assert tw_names.zh_name("9999.TW") == "測試公司"
    assert tw_names.zh_name("2317.TW") == "鴻海"  # built-in still fills gaps
    tw_names._names = None  # new process: reads the fresh cache, no download
    assert tw_names.zh_name("9999.TWO") == "測試公司"
    assert calls == [1]


def test_stale_cache_is_used_when_refresh_fails(monkeypatch):
    tw_names.CACHE.parent.mkdir(parents=True, exist_ok=True)
    tw_names.CACHE.write_text(json.dumps({"8888": "舊名單公司"}, ensure_ascii=False), encoding="utf-8")
    old = time.time() - tw_names.MAX_AGE - 10
    os.utime(tw_names.CACHE, (old, old))
    monkeypatch.setattr(tw_names, "_refresh", lambda: {})
    assert tw_names.zh_name("8888.TW") == "舊名單公司"


def test_failed_refresh_is_not_retried_every_call(monkeypatch):
    calls = []
    monkeypatch.setattr(tw_names, "_refresh", lambda: calls.append(1) or {})
    for _ in range(5):
        tw_names._names = None
        tw_names.zh_name("2330.TW")
    assert calls == [1]


def test_screener_table_uses_chinese_names(monkeypatch):
    import numpy as np

    from tradingagents import screener

    idx = pd.bdate_range("2025-01-01", periods=300)
    price = pd.Series(np.linspace(100, 130, len(idx)), index=idx)
    hist = pd.DataFrame({"Open": price, "High": price * 1.01, "Low": price * 0.99, "Close": price,
                         "Volume": 5e7}, index=idx)
    table = screener.build_feature_table(
        ["2454.TW", "NVDA"], "2025-12-31",
        history_fn=lambda ts, as_of: dict.fromkeys(ts, hist),
        profile_fn=lambda ts: {t: {"name": "MEDIATEK INC" if t.startswith("2454") else "NVIDIA Corp"} for t in ts},
        min_traded_value={"TW": 0, "US": 0})
    assert table.loc["2454.TW", "name"] == "聯發科"
    assert table.loc["NVDA", "name"] == "NVIDIA Corp"


def test_alert_messages_include_chinese_name():
    import numpy as np

    from webapp import alerts

    idx = pd.bdate_range("2025-01-01", periods=80)
    close = pd.Series(np.r_[np.full(79, 100.0), 110.0], index=idx)
    hist = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 1e6})
    rules = {**alerts.DEFAULT_RULES, "daily_move_pct": 5.0}
    msgs = [m for _, m in alerts.check_ticker("2330.TW", hist, rules)]
    assert any("2330.TW 台積電" in m for m in msgs), msgs
