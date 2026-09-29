"""Screener: point-in-time features, per-market ranking, and the report stage."""

import numpy as np
import pandas as pd
import pytest

from tradingagents.screener import build_feature_table, price_features, screen


def bars(daily_ret, n=300, vol=1e6, last_vol=None, seed=0):
    rng = np.random.default_rng(seed)
    r = daily_ret + rng.normal(0, 0.005, n)
    close = 100 * np.cumprod(1 + r)
    volume = np.full(n, vol)
    if last_vol is not None:
        volume[-5:] = last_vol
    idx = pd.bdate_range(end="2026-09-25", periods=n)
    return pd.DataFrame({"Close": close, "Volume": volume}, index=idx)


def test_price_features_needs_a_year():
    assert price_features(bars(0.001, n=200)) is None
    f = price_features(bars(0.002))
    assert f["ret_12_1"] > 0 and f["above_sma200"] and f["trend_short"]
    assert 0 <= f["rsi14"] <= 100


HIST = {
    "UP.TW": bars(0.003, last_vol=3e6, seed=1),
    "FLAT.TW": bars(0.0, seed=2),
    "DOWN.TW": bars(-0.002, seed=3),
    "UP": bars(0.003, seed=4),
    "DOWN": bars(-0.002, seed=5),
    "SHORT": bars(0.003, n=100, seed=6),
}
PROF = {
    "UP.TW": {"name": "Up TW", "returnOnEquity": 0.30, "revenueGrowth": 0.2, "earningsGrowth": 0.25,
                  "profitMargins": 0.3, "debtToEquity": 20, "forwardPE": 18},
    "FLAT.TW": {"name": "Flat TW", "returnOnEquity": 0.10, "revenueGrowth": 0.02, "earningsGrowth": 0.0,
                    "profitMargins": 0.1, "debtToEquity": 80, "forwardPE": 15},
    "DOWN.TW": {"name": "Down TW", "returnOnEquity": -0.05, "revenueGrowth": -0.1, "earningsGrowth": -0.3,
                    "profitMargins": -0.02, "debtToEquity": 150, "forwardPE": -10},
    "UP": {"name": "Up US", "returnOnEquity": 0.25, "revenueGrowth": 0.15, "earningsGrowth": 0.2,
               "profitMargins": 0.25, "debtToEquity": 40, "forwardPE": 25},
    "DOWN": {"name": "Down US", "returnOnEquity": 0.02, "revenueGrowth": -0.05, "earningsGrowth": None,
                 "profitMargins": 0.01, "debtToEquity": 200, "forwardPE": 40},
}


@pytest.fixture
def table():
    return build_feature_table(
        list(HIST), "2026-09-25",
        history_fn=lambda t, d: {k: HIST[k] for k in t},
        profile_fn=lambda ts: {t: PROF.get(t, {}) for t in ts},
        min_traded_value={"TW": 0, "US": 0},
    )


def test_short_history_dropped(table):
    assert "SHORT" not in table.index
    assert set(table["market"]) == {"TW", "US"}


@pytest.mark.parametrize("horizon", ["short", "long"])
def test_best_name_ranks_first_within_each_market(table, horizon):
    picks = screen(table, horizon, top_n=1)
    assert {(p.market, p.ticker) for p in picks} == {("TW", "UP.TW"), ("US", "UP")}
    assert all(p.reason.endswith("。") for p in picks)


def test_long_reason_mentions_fundamentals(table):
    pick = next(p for p in screen(table, "long", top_n=1) if p.ticker == "UP.TW")
    assert "ROE" in pick.reason and "200 日線" in pick.reason


def test_liquidity_floor_drops_thin_names():
    t = build_feature_table(
        ["UP.TW"], "2026-09-25",
        history_fn=lambda t, d: {"UP.TW": HIST["UP.TW"]},
        profile_fn=lambda ts: {}, min_traded_value={"TW": 1e12},
    )
    assert t.empty


def test_decision_field_parsing():
    from recommend import decision_field
    text = ("**Rating**: Buy\n\n**Executive Summary**: Build over 3 months.\nSecond line.\n\n"
            "**Investment Thesis**: Strong moat.\n\n**Price Target**: 1200.0\n\n**Time Horizon**: 12 months")
    assert decision_field(text, "Executive Summary") == "Build over 3 months.\nSecond line."
    assert decision_field(text, "Price Target") == "1200.0"
    assert decision_field(text, "Time Horizon") == "12 months"
    assert decision_field("", "Rating") == ""


def test_screen_only_report(monkeypatch, tmp_path, table):
    import recommend
    monkeypatch.setattr(recommend, "build_feature_table", lambda u, d: table)
    code = recommend.main(["--screen-only", "--top", "1", "--date", "2026-09-25", "--out", str(tmp_path)])
    assert code == 0
    report = next(tmp_path.glob("recommendations_*.md")).read_text(encoding="utf-8")
    assert "短線" in report and "中長期" in report and "UP.TW" in report and "量化篩選理由" in report


def test_debate_keeps_only_buy_and_overweight(monkeypatch, tmp_path, table):
    import recommend

    class FakeGraph:
        def __init__(self, config, callbacks=None):
            self.horizon = config["investment_horizon"]

        def propagate(self, ticker, date, portfolio=None):
            rating = "Buy" if ticker == "UP.TW" else "Hold"
            dec = (f"**Rating**: {rating}\n\n**Executive Summary**: plan for {ticker}\n\n"
                   "**Investment Thesis**: because\n\n**Price Target**: 100\n\n**Time Horizon**: 6 months")
            return {"final_trade_decision": dec}, rating

        def save_reports(self, state, ticker):
            pass

    monkeypatch.setattr(recommend, "build_feature_table", lambda u, d: table)
    monkeypatch.setattr(recommend, "TradingAgentsGraph", FakeGraph)
    assert recommend.main(["--top", "1", "--date", "2026-09-25", "--out", str(tmp_path)]) == 0
    report = next(tmp_path.glob("recommendations_*.md")).read_text(encoding="utf-8")
    assert "| 台股 | UP.TW | Up TW | Buy | 100 | 6 months |" in report
    assert "- UP Up US（Hold）：plan for UP" in report
