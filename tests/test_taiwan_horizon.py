"""Taiwan listings resolve to Taiwan benchmarks; the investment horizon reaches
the agents and sets the outcome window."""

from tradingagents.agents.context import build_horizon_instruction
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.settlement import resolve_benchmark, resolve_holding_days


def test_taiwan_suffixes_resolve_to_taiwan_indices():
    assert resolve_benchmark("2330.TW", DEFAULT_CONFIG) == "^TWII"
    assert resolve_benchmark("6488.TWO", DEFAULT_CONFIG) == "006201.TWO"
    assert resolve_benchmark("0050.tw", DEFAULT_CONFIG) == "^TWII"


def test_other_markets_unchanged():
    assert resolve_benchmark("NVDA", DEFAULT_CONFIG) == "SPY"
    assert resolve_benchmark("7203.T", DEFAULT_CONFIG) == "^N225"
    assert resolve_benchmark("RY.TO", DEFAULT_CONFIG) == "^GSPTSE"


def test_holding_days_follow_horizon_unless_explicit():
    base = {"horizon_holding_days": {"short": 5, "long": 63}}
    assert resolve_holding_days({**base, "investment_horizon": "short"}) == 5
    assert resolve_holding_days({**base, "investment_horizon": "long"}) == 63
    assert resolve_holding_days({**base, "investment_horizon": "long", "holding_period_days": 21}) == 21
    assert resolve_holding_days({}) == 5
    assert resolve_holding_days(DEFAULT_CONFIG) == 5


def test_horizon_instruction():
    assert "SHORT-TERM" in build_horizon_instruction("short")
    assert "LONG-TERM" in build_horizon_instruction("Long")
    assert build_horizon_instruction(None) == ""
    assert build_horizon_instruction("weird") == ""
