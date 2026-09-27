"""A model that puts an indicator name in ``symbol`` (seen live: yfinance asked
for tickers "MACD", "BOLL_UB", "VWMA") gets the run's ticker instead."""

from unittest import mock

import pytest
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from tradingagents.agents import tools


class _State(MessagesState):
    trade_date: str
    company_of_interest: str


def _routed(tool, args):
    graph = StateGraph(_State)
    graph.add_node("tools", ToolNode([tool]))
    graph.add_edge(START, "tools")
    graph.add_edge("tools", END)
    with mock.patch.object(tools, "route_to_vendor", return_value="ok") as routed:
        graph.compile().invoke({
            "messages": [AIMessage("", tool_calls=[{"name": tool.name, "args": args, "id": "1"}])],
            "trade_date": "2026-09-25", "company_of_interest": "2330.TW",
        })
    return [c.args for c in routed.call_args_list]


@pytest.mark.unit
@pytest.mark.parametrize("bad", ["MACD", "boll_ub", "VWMA"])
def test_indicator_in_symbol_reads_as_run_ticker(bad):
    calls = _routed(tools.get_indicators,
                    {"symbol": bad, "indicator": "rsi", "curr_date": "2026-09-25"})
    assert calls == [("get_indicators", "2330.TW", "rsi", "2026-09-25", 30)]


@pytest.mark.unit
def test_swapped_arguments_keep_the_indicator():
    calls = _routed(tools.get_indicators,
                    {"symbol": "MACD", "indicator": "2330.TW", "curr_date": "2026-09-25"})
    assert calls == [("get_indicators", "2330.TW", "macd", "2026-09-25", 30)]


@pytest.mark.unit
def test_stock_data_with_indicator_symbol():
    calls = _routed(tools.get_stock_data,
                    {"symbol": "VWMA", "start_date": "2026-09-01", "end_date": "2026-09-25"})
    assert calls == [("get_stock_data", "2330.TW", "2026-09-01", "2026-09-25")]


@pytest.mark.unit
def test_real_other_ticker_is_left_alone():
    calls = _routed(tools.get_stock_data,
                    {"symbol": "^TWII", "start_date": "2026-09-01", "end_date": "2026-09-25"})
    assert calls[0][1] == "^TWII"


@pytest.mark.unit
def test_run_ticker_hidden_from_model():
    for t in (tools.get_stock_data, tools.get_indicators, tools.get_verified_market_snapshot):
        assert "run_ticker" not in t.tool_call_schema.model_json_schema()["properties"]
