"""Traditional-Chinese financial news from RSS: Yahoo奇摩股市 category feeds and
Google News (zh-TW) searches for individual stocks. Items use the same dict
shape as the Yahoo Finance news (title, summary, publisher, link, pub_date)."""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import streamlit as st

from webapp.data import DEMO

YAHOO_TW_FEEDS = {
    "台股": "https://tw.stock.yahoo.com/rss?category=tw-market",
    "國際財經": "https://tw.stock.yahoo.com/rss?category=intl-markets",
    "最新": "https://tw.stock.yahoo.com/rss?category=news",
    "研究報告": "https://tw.stock.yahoo.com/rss?category=research",
}
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def _clean(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html.unescape(text or ""))
    return re.sub(r"\s+", " ", text).strip()


def parse_rss(xml_text: str, default_publisher: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = []
    for it in root.iter("item"):
        title = _clean(it.findtext("title"))
        src = it.find("source")
        publisher = _clean(src.text) if src is not None and src.text else default_publisher
        # Google News titles end with " - Publisher"; keep the headline only.
        if src is not None and title.endswith(f" - {publisher}"):
            title = title[: -len(publisher) - 3]
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate") or "")
            pub = pub if pub.tzinfo else pub.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            pub = None
        summary = _clean(it.findtext("description"))
        if summary.startswith(title):
            summary = ""
        items.append({"title": title, "summary": summary[:500], "publisher": publisher,
                      "link": (it.findtext("link") or "").strip(), "pub_date": pub})
    return items


def _get(url: str) -> str:
    import requests

    r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9"}, timeout=15)
    r.raise_for_status()
    return r.text


def _demo(label: str, n: int = 6) -> list[dict]:
    now = datetime.now(timezone.utc)
    return [{"title": f"[Demo] {label} 中文新聞標題 {i + 1}", "summary": "demo 模式的中文新聞摘要。",
             "publisher": ["經濟日報", "鉅亨網", "工商時報"][i % 3], "link": f"https://example.com/zh/{i}",
             "pub_date": now - timedelta(hours=3 * i + 1)} for i in range(n)]


@st.cache_data(ttl=900, show_spinner=False)
def yahoo_tw(category: str) -> list[dict]:
    if DEMO:
        return _demo(category)
    try:
        return parse_rss(_get(YAHOO_TW_FEEDS[category]), "Yahoo股市")
    except Exception:  # noqa: BLE001 — a dead feed shows as "no news"
        return []


@st.cache_data(ttl=900, show_spinner=False)
def google_news(query: str, days: int = 14) -> list[dict]:
    if DEMO:
        return _demo(query, 5)
    url = (f"https://news.google.com/rss/search?q={quote(query + f' when:{days}d')}"
           "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")
    try:
        return parse_rss(_get(url), "Google 新聞")
    except Exception:  # noqa: BLE001
        return []


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def chinese_name(ticker: str) -> str | None:
    """Chinese short name of a Taiwan stock (FinMind TaiwanStockInfo), else None."""
    from webapp import twdata

    sid = twdata.stock_id(ticker)
    if not sid or DEMO:
        return None
    try:
        info = twdata.fetch("TaiwanStockInfo", sid, "2000-01-01")
        return str(info["stock_name"].iloc[0]) if not info.empty and "stock_name" in info else None
    except Exception:  # noqa: BLE001
        return None


def stock_news(ticker: str) -> list[dict]:
    """Chinese news for one stock: '<code> <中文名>' for Taiwan, '<ticker> 股價' otherwise."""
    from webapp import twdata

    sid = twdata.stock_id(ticker)
    if sid:
        name = chinese_name(ticker)
        return google_news(f"{sid} {name}" if name else f"{sid} 股")
    return google_news(f"{ticker} 股價")
