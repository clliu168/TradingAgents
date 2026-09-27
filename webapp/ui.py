"""Shared UI pieces: watchlist storage, formatting, news list, AI digest."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import streamlit as st

from webapp.jobs import DATA_DIR

WATCHLIST_FILE = DATA_DIR / "watchlist.json"
DEFAULT_WATCHLIST = ["2330.TW", "2454.TW", "2317.TW", "0050.TW", "NVDA", "MSFT", "GOOGL", "TSM"]
DISCLAIMER = "資料來源：Yahoo Finance（可能延遲）。本工具產出僅供研究參考，不構成投資建議。"


def load_watchlist() -> list[str]:
    try:
        data = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
        return [t for t in data if isinstance(t, str)] or DEFAULT_WATCHLIST
    except (OSError, ValueError):
        return list(DEFAULT_WATCHLIST)


def save_watchlist(tickers: list[str]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WATCHLIST_FILE.write_text(json.dumps(tickers, ensure_ascii=False, indent=1), encoding="utf-8")


def normalize_ticker(raw: str) -> str:
    t = raw.strip().upper()
    # A bare 4-digit Taiwan code, or a 5-6 digit ETF code starting with 00, means TWSE.
    if t.isdigit() and (len(t) == 4 or (t.startswith("00") and len(t) in (5, 6))):
        t += ".TW"
    return t


def fmt_pct(x, digits: int = 2) -> str:
    try:
        return f"{float(x):+.{digits}%}"
    except (TypeError, ValueError):
        return "—"


def fmt_num(x, digits: int = 2) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "—"
    for unit, div in (("兆", 1e12), ("億", 1e8)):
        if abs(x) >= div:
            return f"{x / div:,.{digits}f} {unit}"
    return f"{x:,.{digits}f}"


def ago(dt: datetime | None) -> str:
    if not dt:
        return ""
    delta = datetime.now(timezone.utc) - dt
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return f"{max(int(delta.total_seconds() // 60), 1)} 分鐘前"
    if hours < 48:
        return f"{int(hours)} 小時前"
    return dt.astimezone().strftime("%Y-%m-%d")


def news_list(articles: list[dict], limit: int = 12, key: str = "news") -> None:
    if not articles:
        st.info("目前抓不到相關新聞。")
        return
    for a in articles[:limit]:
        with st.container(border=True):
            title = a["title"]
            st.markdown(f"**[{title}]({a['link']})**" if a.get("link") else f"**{title}**")
            st.caption(f"{a.get('publisher', '')}　·　{ago(a.get('pub_date'))}")
            if a.get("summary"):
                st.write(a["summary"][:400] + ("…" if len(a["summary"]) > 400 else ""))


def ai_digest_block(articles: list[dict], topic: str, key: str) -> None:
    """Button that asks the configured LLM for a Chinese digest of the headlines."""
    state_key = f"digest_{key}"
    if st.button("🤖 AI 新聞重點整理", key=f"btn_{key}", help="用 .env 設定的模型（quick_think）整理，會產生少量 API 費用"):
        with st.spinner("整理中…"):
            try:
                from webapp.services import ai_digest

                content = ai_digest(articles, topic)
                if isinstance(content, list):
                    content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
                st.session_state[state_key] = content
            except Exception as exc:  # noqa: BLE001
                st.session_state[state_key] = f"⚠️ 無法產生摘要：{exc}"
    if st.session_state.get(state_key):
        with st.container(border=True):
            st.markdown(st.session_state[state_key])


def open_stock(ticker: str) -> None:
    st.session_state["stock_ticker"] = ticker
    st.switch_page("views/stock.py")
