"""TradingAgents 投資儀表板 — run from the repo root:

    streamlit run webapp/app.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from webapp.data import DEMO  # noqa: E402
from webapp.ui import DISCLAIMER, load_watchlist, normalize_ticker, save_watchlist  # noqa: E402

st.set_page_config(page_title="TradingAgents 投資儀表板", page_icon="📈", layout="wide")

pages = {
    "市場": [
        st.Page("views/overview.py", title="大盤總覽", icon="🌏", default=True),
        st.Page("views/stock.py", title="個股分析", icon="📊"),
        st.Page("views/compare.py", title="多檔比較", icon="⚖️"),
        st.Page("views/news.py", title="新聞", icon="📰"),
        st.Page("views/calendar.py", title="行事曆", icon="📅"),
    ],
    "AI 分析": [
        st.Page("views/generate.py", title="產生報告", icon="🤖"),
        st.Page("views/reports.py", title="報告與建議", icon="📑"),
        st.Page("views/performance.py", title="績效追蹤", icon="🎯"),
    ],
    "我的": [
        st.Page("views/holdings.py", title="我的持倉", icon="💼"),
        st.Page("views/settings.py", title="設定與費用", icon="⚙️"),
    ],
}
nav = st.navigation(pages)

with st.sidebar:
    st.markdown("### ⭐ 自選股")
    wl = load_watchlist()
    edited = st.text_area("每行一檔（台股可只打代號，如 2330）", "\n".join(wl), height=180, key="wl_text")
    if st.button("儲存自選股", width="stretch"):
        tickers = [normalize_ticker(x) for x in edited.replace(",", "\n").splitlines() if x.strip()]
        save_watchlist(list(dict.fromkeys(tickers)))
        st.success("已儲存")
        st.rerun()
    if DEMO:
        st.warning("DEMO 模式：使用模擬資料")
    st.caption(DISCLAIMER)

nav.run()
