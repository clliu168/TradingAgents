import streamlit as st

from webapp import data
from webapp.ui import ai_digest_block, load_watchlist, news_list, page_timestamp

st.title("📰 新聞")
page_timestamp()
st.caption("新聞來自 Yahoo Finance，多為英文；點標題開啟原文。每篇的「摘要與重點」會讀取原文後用 .env 設定的模型整理成中文，"
           "結果會存起來，同一篇不會重複計費。最上方的「AI 新聞重點整理」則是把整頁新聞彙整成一份概覽。")

tabs = st.tabs(["台股", "美股", "總經與地緣", "⭐ 自選股"])
for tab, topic in zip(tabs[:3], data.MARKET_NEWS_QUERIES, strict=False):
    with tab:
        articles = data.market_news(topic)
        ai_digest_block(articles, f"{topic}市場", key=f"market_{topic}")
        news_list(articles, limit=15, key=f"market_{topic}")

with tabs[3]:
    wl = load_watchlist()
    pick = st.selectbox("股票", wl) if wl else None
    if pick:
        articles = data.ticker_news(pick)
        ai_digest_block(articles, pick, key=f"wl_{pick}")
        news_list(articles, limit=15, key=f"wl_{pick}")
