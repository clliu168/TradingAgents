"""Shared UI pieces: watchlist storage, formatting, news list, AI digest."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd
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


TAIPEI = ZoneInfo("Asia/Taipei")
_WEEKDAYS = "一二三四五六日"


def now_taipei() -> datetime:
    return datetime.now(TAIPEI)


def fmt_bar_date(ts) -> str:
    """Date of a daily bar, e.g. '2026-09-26（五）'; today's bar is flagged as possibly intraday."""
    d = pd.Timestamp(ts).date()
    label = f"{d:%Y-%m-%d}（{_WEEKDAYS[d.weekday()]}）"
    if d == now_taipei().date():
        label += "・今日，盤中可能未收盤"
    return label


def page_timestamp() -> None:
    st.caption(f"頁面更新：{now_taipei():%Y-%m-%d %H:%M}（台北時間）・行情約每 10 分鐘更新・資料來源 Yahoo Finance，可能延遲")


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


SENTIMENT_ICON = {"偏多": "🔴 偏多", "偏空": "🟢 偏空", "中性": "⚪ 中性"}


def _render_summary(res: dict) -> None:
    st.markdown(f"**摘要**：{res.get('summary', '')}")
    if res.get("points"):
        st.markdown("**重點**\n" + "\n".join(f"- {p}" for p in res["points"]))
    extra = []
    if res.get("impact"):
        extra.append(f"**可能影響**：{res['impact']}")
    if res.get("sentiment"):
        extra.append(f"**語氣**：{SENTIMENT_ICON.get(res['sentiment'], res['sentiment'])}")
    if res.get("tickers"):
        extra.append("**相關代碼**：" + "、".join(res["tickers"]))
    if extra:
        st.markdown("　｜　".join(extra))
    st.caption(f"AI 整理（依據：{res.get('source', '')}），可能有誤，請以原文為準。")


def news_list(articles: list[dict], limit: int = 12, key: str = "news") -> None:
    """Article cards; each has an AI summary + key points (cached per article)."""
    from webapp import articles as art

    if not articles:
        st.info("目前抓不到相關新聞。")
        return
    from webapp.usage import over_budget

    shown = articles[:limit]
    todo = [a for a in shown if not art.cached(a.get("link") or a["title"])]
    blocked, why = over_budget()
    if blocked and todo:
        st.caption(f"🚫 AI 摘要暫停：{why}")
    if todo and not blocked and st.button(f"🤖 為本頁 {len(todo)} 篇文章產生摘要與重點", key=f"batch_{key}",
                          help="逐篇讀取原文後用 quick_think 模型整理；結果會存起來，同一篇不會重複計費"):
        bar = st.progress(0.0, text="整理中…")
        llm = art._llm()
        for i, a in enumerate(todo, 1):
            try:
                art.summarize(a, llm=llm)
            except Exception as exc:  # noqa: BLE001
                st.warning(f"「{a['title'][:40]}…」整理失敗：{exc}")
            bar.progress(i / len(todo), text=f"整理中… {i}/{len(todo)}")
        bar.empty()
    for i, a in enumerate(shown):
        with st.container(border=True):
            title = a["title"]
            st.markdown(f"**[{title}]({a['link']})**" if a.get("link") else f"**{title}**")
            st.caption(f"{a.get('publisher', '')}　·　{ago(a.get('pub_date'))}")
            res = art.cached(a.get("link") or title)
            if res:
                _render_summary(res)
            else:
                if a.get("summary"):
                    st.write(a["summary"][:300] + ("…" if len(a["summary"]) > 300 else ""))
                if not blocked and st.button("🤖 摘要與重點", key=f"sum_{key}_{i}"):
                    with st.spinner("讀取原文並整理中…"):
                        try:
                            _render_summary(art.summarize(a))
                        except Exception as exc:  # noqa: BLE001
                            st.warning(f"整理失敗：{exc}")


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


@st.dialog("走勢圖", width="large")
def chart_dialog(ticker: str, name: str | None = None, allow_open: bool = True) -> None:
    """Full time-series view for an index or a stock, opened from a card or a table row."""
    from webapp import charts, data
    from webapp.indicators import add_indicators

    if not name:
        info = data.profile(ticker) if not ticker.startswith("^") else {}
        name = info.get("longName") or info.get("shortName") or ticker
    st.markdown(f"### {name}（{ticker}）" if name != ticker else f"### {ticker}")
    c1, c2, c3 = st.columns([2, 2, 3])
    period = c1.selectbox("期間", list(data.PERIOD_DAYS), index=3, key=f"dlg_p_{ticker}")
    style = c2.radio("圖型", ["K 線", "折線"], horizontal=True, key=f"dlg_s_{ticker}")
    mas = c3.multiselect("均線", ["SMA20", "SMA60", "SMA240"], default=["SMA20", "SMA60"],
                         format_func=lambda s: s.replace("SMA", "MA"), key=f"dlg_m_{ticker}")
    hist = data.history(ticker, data.PERIOD_DAYS[period])
    if hist.empty:
        st.error("抓不到這個代碼的歷史資料。")
        return
    ind = add_indicators(hist)
    cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=data.PERIOD_DAYS[period])
    view = ind[ind.index >= cutoff]
    first, last = view["Close"].iloc[0], view["Close"].iloc[-1]
    st.caption(f"期間：{view.index[0]:%Y-%m-%d} ～ {fmt_bar_date(view.index[-1])}")
    m = st.columns(4)
    m[0].metric("最新", f"{last:,.2f}")
    m[1].metric(f"{period}漲跌", fmt_pct(last / first - 1))
    m[2].metric("期間最高", f"{view['High'].max():,.2f}")
    m[3].metric("期間最低", f"{view['Low'].min():,.2f}")
    if style == "K 線":
        fig = charts.price_chart(view, "", mas, False, [])
    else:
        fig = charts.line_chart(view, mas)
    st.plotly_chart(fig, width="stretch", key=f"dlg_c_{ticker}")
    if allow_open and st.button("📊 開啟完整個股分析", key=f"dlg_o_{ticker}"):
        open_stock(ticker)


def open_stock(ticker: str) -> None:
    st.session_state["stock_ticker"] = ticker
    st.switch_page("views/stock.py")
