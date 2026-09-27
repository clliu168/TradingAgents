import streamlit as st

from webapp import data
from webapp.ui import ai_digest_block, load_watchlist, news_list

st.title("📰 新聞")
st.caption("新聞來自 Yahoo Finance，多為英文；點標題開啟原文。AI 重點整理會用您 .env 設定的模型，產生少量費用。")

tabs = st.tabs(["台股", "美股", "總經與地緣", "⭐ 自選股"])
for tab, (topic, queries) in zip(tabs[:3], data.MARKET_NEWS_QUERIES.items(), strict=False):
    with tab:
        articles = data.search_news(queries)
        ai_digest_block(articles, f"{topic}市場", key=f"market_{topic}")
        news_list(articles, limit=15, key=f"market_{topic}")

with tabs[3]:
    wl = load_watchlist()
    pick = st.selectbox("股票", wl) if wl else None
    if pick:
        articles = data.ticker_news(pick)
        ai_digest_block(articles, pick, key=f"wl_{pick}")
        news_list(articles, limit=15, key=f"wl_{pick}")
