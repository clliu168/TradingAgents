import streamlit as st

from webapp import cnnews, data
from webapp.ui import ai_digest_block, load_watchlist, news_list, page_timestamp

st.title("📰 新聞")
page_timestamp()
st.caption("中文新聞來自 Yahoo奇摩股市與 Google 新聞，英文新聞來自 Yahoo Finance；點標題開啟原文。"
           "每篇的「摘要與重點」會讀取原文後用 AI 整理成中文（結果會存起來，同一篇不會重複計費）；"
           "最上方的「AI 新聞重點整理」則是把整頁新聞彙整成一份概覽。")

tabs = st.tabs(["🇹🇼 台股（中文）", "🌐 國際財經（中文）", "台股（英文）", "美股（英文）", "總經與地緣（英文）", "⭐ 自選股"])

with tabs[0]:
    articles = cnnews.yahoo_tw("台股")
    ai_digest_block(articles, "台股市場", key="zh_tw")
    news_list(articles, limit=20, key="zh_tw")

with tabs[1]:
    articles = cnnews.yahoo_tw("國際財經")
    ai_digest_block(articles, "國際財經", key="zh_intl")
    news_list(articles, limit=20, key="zh_intl")

for tab, topic in zip(tabs[2:5], data.MARKET_NEWS_QUERIES, strict=False):
    with tab:
        articles = data.market_news(topic)
        ai_digest_block(articles, f"{topic}市場", key=f"market_{topic}")
        news_list(articles, limit=15, key=f"market_{topic}")

with tabs[5]:
    wl = load_watchlist()
    c1, c2 = st.columns([2, 1])
    pick = c1.selectbox("股票", wl) if wl else None
    lang = c2.radio("來源", ["中文", "英文", "全部"], horizontal=True)
    if pick:
        zh = cnnews.stock_news(pick) if lang != "英文" else []
        en = data.ticker_news(pick) if lang != "中文" else []
        articles = data._sorted_unique(zh + en)
        ai_digest_block(articles, pick, key=f"wl_{pick}_{lang}")
        news_list(articles, limit=20, key=f"wl_{pick}_{lang}")
