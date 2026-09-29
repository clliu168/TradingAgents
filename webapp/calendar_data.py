"""Upcoming events: macro releases (hand-maintained list) and, for the watchlist
and holdings, earnings dates and ex-dividend dates."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from webapp.data import DEMO
from webapp.jobs import DATA_DIR

MACRO_FILE = DATA_DIR / "macro_events.json"
ET = ZoneInfo("America/New_York")
TPE = ZoneInfo("Asia/Taipei")

# Checked against federalreserve.gov (FOMC calendar) and bls.gov (2026 release
# schedule) on 2026-09-29. FOMC dates after the next meeting are tentative.
# Times are US Eastern; the page converts them to Taipei time.
DEFAULT_MACRO = [
    {"date": "2026-10-02", "time_et": "08:30", "event": "美國就業報告（9 月非農）", "source": "BLS"},
    {"date": "2026-10-14", "time_et": "08:30", "event": "美國 CPI（9 月）", "source": "BLS"},
    {"date": "2026-10-28", "time_et": "14:00", "event": "FOMC 利率決議（10/27–28 會議）", "source": "Federal Reserve"},
    {"date": "2026-11-06", "time_et": "08:30", "event": "美國就業報告（10 月非農）", "source": "BLS"},
    {"date": "2026-11-10", "time_et": "08:30", "event": "美國 CPI（10 月）", "source": "BLS"},
    {"date": "2026-12-04", "time_et": "08:30", "event": "美國就業報告（11 月非農）", "source": "BLS"},
    {"date": "2026-12-09", "time_et": "14:00", "event": "FOMC 利率決議（12/8–9 會議，含經濟預測）", "source": "Federal Reserve"},
    {"date": "2026-12-10", "time_et": "08:30", "event": "美國 CPI（11 月）", "source": "BLS"},
    {"date": "2027-01-27", "time_et": "14:00", "event": "FOMC 利率決議（暫定）", "source": "Federal Reserve"},
    {"date": "2027-03-17", "time_et": "14:00", "event": "FOMC 利率決議（暫定）", "source": "Federal Reserve"},
]


def macro_events() -> list[dict]:
    try:
        return json.loads(MACRO_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return list(DEFAULT_MACRO)


def save_macro(events: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MACRO_FILE.write_text(json.dumps(events, ensure_ascii=False, indent=1), encoding="utf-8")


def to_taipei(d: str, time_et: str | None) -> datetime | None:
    if not time_et:
        return None
    h, m = (int(x) for x in time_et.split(":"))
    et = datetime.fromisoformat(d).replace(hour=h, minute=m, tzinfo=ET)
    return et.astimezone(TPE)


def _as_dates(v) -> list[date]:
    if v is None:
        return []
    vals = v if isinstance(v, (list, tuple)) else [v]
    out = []
    for x in vals:
        try:
            out.append(pd.Timestamp(x).date())
        except (TypeError, ValueError):
            continue
    return out


@st.cache_data(ttl=12 * 3600, show_spinner=False)
def company_events(ticker: str) -> list[dict]:
    """Earnings / ex-dividend / dividend-payment dates for one ticker."""
    if DEMO:
        today = date.today()
        return [{"date": today + timedelta(days=10 + len(ticker)), "ticker": ticker, "event": "財報公布（預估）"},
                {"date": today + timedelta(days=25), "ticker": ticker, "event": "除息交易日"}]
    events = []
    from webapp import twdata

    sid = twdata.stock_id(ticker)
    if sid:
        try:
            for _, r in twdata.dividends(sid).iterrows():
                if pd.notna(r.get("除息交易日")):
                    events.append({"date": r["除息交易日"].date(), "ticker": ticker,
                                   "event": f"除息交易日（現金股利 {r['現金股利']:.2f} 元）"})
                if pd.notna(r.get("除權交易日")):
                    events.append({"date": r["除權交易日"].date(), "ticker": ticker, "event": "除權交易日"})
                if pd.notna(r.get("發放日")):
                    events.append({"date": r["發放日"].date(), "ticker": ticker, "event": "現金股利發放日"})
        except Exception:  # noqa: BLE001 — no token / no data: fall back to Yahoo below
            pass
    try:
        import yfinance as yf

        cal = yf.Ticker(ticker).calendar or {}
    except Exception:  # noqa: BLE001
        cal = {}
    for d in _as_dates(cal.get("Earnings Date")):
        events.append({"date": d, "ticker": ticker, "event": "財報公布（Yahoo 預估）"})
    if not sid:
        for d in _as_dates(cal.get("Ex-Dividend Date")):
            events.append({"date": d, "ticker": ticker, "event": "除息日"})
        for d in _as_dates(cal.get("Dividend Date")):
            events.append({"date": d, "ticker": ticker, "event": "股利發放日"})
    return events
