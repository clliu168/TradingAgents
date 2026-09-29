"""LLM usage and cost: a LangChain callback that logs tokens per call, a price
table, and a monthly/daily budget that the daily job and the web buttons check.

Log: webapp_data/usage.jsonl, one JSON object per LLM call.
Prices (USD per 1M tokens) default to OpenAI's list prices as of 2026-09;
override them in webapp_data/pricing.json from the 設定 page.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from langchain_core.callbacks import BaseCallbackHandler

from webapp.jobs import DATA_DIR

USAGE_FILE = DATA_DIR / "usage.jsonl"
PRICING_FILE = DATA_DIR / "pricing.json"
BUDGET_FILE = DATA_DIR / "budget.json"
TZ = ZoneInfo("Asia/Taipei")

# USD per 1M tokens (input, cached input, output). Source: OpenAI API pricing page, 2026-09.
DEFAULT_PRICES = {
    "gpt-6-astra": [10.00, 1.00, 50.00],
    "gpt-6-sol": [2.00, 0.20, 10.00],
    "gpt-6-luna": [0.10, 0.01, 0.50],
}
DEFAULT_BUDGET = {"monthly_usd": 400.0, "daily_usd": 30.0}
_lock = threading.Lock()


class UsageRecorder(BaseCallbackHandler):
    """Append one line per finished LLM call to the usage log."""

    def __init__(self, source: str, path: Path | None = None):
        self.source = source
        self.path = path or USAGE_FILE
        self._models: dict[Any, str] = {}

    def _remember(self, run_id, serialized, kwargs):
        params = kwargs.get("invocation_params") or {}
        model = params.get("model") or params.get("model_name") or (serialized or {}).get("kwargs", {}).get("model")
        if model:
            self._models[run_id] = str(model)

    def on_chat_model_start(self, serialized, messages, *, run_id=None, **kwargs):
        self._remember(run_id, serialized, kwargs)

    def on_llm_start(self, serialized, prompts, *, run_id=None, **kwargs):
        self._remember(run_id, serialized, kwargs)

    def on_llm_end(self, response, *, run_id=None, **kwargs):
        inp = out = cached = 0
        model = self._models.pop(run_id, None)
        for gens in response.generations or []:
            for g in gens:
                msg = getattr(g, "message", None)
                meta = getattr(msg, "usage_metadata", None) or {}
                inp += int(meta.get("input_tokens") or 0)
                out += int(meta.get("output_tokens") or 0)
                cached += int((meta.get("input_token_details") or {}).get("cache_read") or 0)
                rmeta = getattr(msg, "response_metadata", None) or {}
                model = model or rmeta.get("model_name") or rmeta.get("model")
        if not (inp or out):
            tu = (response.llm_output or {}).get("token_usage") or {}
            inp, out = int(tu.get("prompt_tokens") or 0), int(tu.get("completion_tokens") or 0)
            model = model or (response.llm_output or {}).get("model_name")
        record(self.source, model or "unknown", inp, out, cached, self.path)


def record(source: str, model: str, inp: int, out: int, cached: int = 0, path: Path | None = None) -> None:
    path = path or USAGE_FILE
    line = json.dumps({"ts": datetime.now(TZ).isoformat(timespec="seconds"), "source": source,
                       "model": model, "input": inp, "output": out, "cached": cached})
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def _read_json(path: Path, default):
    try:
        return {**default, **json.loads(path.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(default)


def prices() -> dict[str, list[float]]:
    return _read_json(PRICING_FILE, DEFAULT_PRICES)


def save_prices(p: dict) -> None:
    PRICING_FILE.parent.mkdir(parents=True, exist_ok=True)
    PRICING_FILE.write_text(json.dumps(p, indent=1), encoding="utf-8")


def budget() -> dict:
    return _read_json(BUDGET_FILE, DEFAULT_BUDGET)


def save_budget(b: dict) -> None:
    BUDGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    BUDGET_FILE.write_text(json.dumps(b, indent=1), encoding="utf-8")


def _price_for(model: str, table: dict) -> list[float] | None:
    m = model.lower()
    if m in table:
        return table[m]
    # Dated or suffixed variants (e.g. gpt-6-sol-2026-08-01) use their base price.
    for name in sorted(table, key=len, reverse=True):
        if m.startswith(name):
            return table[name]
    return None


def load(path: Path | None = None) -> pd.DataFrame:
    path = path or USAGE_FILE
    cols = ["ts", "source", "model", "input", "output", "cached"]
    if not path.exists():
        return pd.DataFrame(columns=[*cols, "cost_usd", "priced"])
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    df = pd.DataFrame(rows, columns=cols)
    df["ts"] = pd.to_datetime(df["ts"])
    table = prices()
    costs, priced = [], []
    for _, r in df.iterrows():
        p = _price_for(str(r["model"]), table)
        priced.append(p is not None)
        if p is None:
            costs.append(0.0)
            continue
        fresh = max(int(r["input"]) - int(r["cached"] or 0), 0)
        costs.append((fresh * p[0] + int(r["cached"] or 0) * p[1] + int(r["output"]) * p[2]) / 1e6)
    df["cost_usd"], df["priced"] = costs, priced
    return df


def spend(df: pd.DataFrame | None = None) -> dict:
    df = load() if df is None else df
    now = datetime.now(TZ)
    if df.empty:
        return {"today": 0.0, "month": 0.0, "last30": 0.0}
    ts = df["ts"].dt.tz_convert(TZ) if df["ts"].dt.tz is not None else df["ts"].dt.tz_localize(TZ)
    return {
        "today": float(df.loc[ts.dt.date == now.date(), "cost_usd"].sum()),
        "month": float(df.loc[(ts.dt.year == now.year) & (ts.dt.month == now.month), "cost_usd"].sum()),
        "last30": float(df.loc[ts >= now - timedelta(days=30), "cost_usd"].sum()),
    }


def over_budget() -> tuple[bool, str]:
    """(True, reason) once today's or this month's spend reaches its cap (0 = no cap)."""
    b, s = budget(), spend()
    if b.get("daily_usd") and s["today"] >= b["daily_usd"]:
        return True, f"今天已花 ${s['today']:.2f}，達到每日上限 ${b['daily_usd']:.2f}"
    if b.get("monthly_usd") and s["month"] >= b["monthly_usd"]:
        return True, f"本月已花 ${s['month']:.2f}，達到每月上限 ${b['monthly_usd']:.2f}"
    return False, ""
