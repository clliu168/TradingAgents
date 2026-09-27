from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from webapp import charts, data
from webapp.indicators import add_indicators
from webapp.ui import ago, chart_dialog, fmt_pct, load_watchlist

st.title("🌏 大盤總覽")

# --- Index cards -----------------------------------------------------------
cards = list(data.INDICES.items())
for row_start in range(0, len(cards), 5):
    cols = st.columns(5)
    for col, (sym, name) in zip(cols, cards[row_start:row_start + 5], strict=False):
        sym, h = data.index_history(sym, 45)
        with col, st.container(border=True):
            if h.empty or len(h) < 2:
                st.metric(name, "—")
                continue
            last, prev = h["Close"].iloc[-1], h["Close"].iloc[-2]
            chg = last / prev - 1
            fmt = f"{last:,.3f}" if sym in ("^TNX", "TWD=X") else f"{last:,.2f}"
            # Taiwan convention: red up, green down (inverse of Streamlit's default).
            st.metric(name, fmt, fmt_pct(chg), delta_color="inverse")
            recent = h["Close"].iloc[-22:]
            st.plotly_chart(charts.sparkline(recent, recent.iloc[-1] >= recent.iloc[0]),
                            width="stretch", config={"displayModeBar": False, "staticPlot": True},
                            key=f"spark_{sym}")
            if sym in data.INDEX_PROXIES.values():
                st.caption(f"以 {sym} 代替")
            if st.button("📈 看走勢", key=f"open_{sym}", width="stretch"):
                chart_dialog(sym, name, allow_open=False)

# --- Relative performance -----------------------------------------------------
st.subheader("指數表現比較")
c1, c2 = st.columns([1, 3])
period = c1.selectbox("期間", list(data.PERIOD_DAYS), index=3)
chosen = c2.multiselect("指數", list(data.INDICES), default=["^TWII", "^TWOII", "^GSPC", "^IXIC", "^SOX"],
                        format_func=lambda s: data.INDICES[s])
if chosen:
    df = data.closes(tuple(data.resolve_index(s) for s in chosen), data.PERIOD_DAYS[period])
    df = df.rename(columns={data.resolve_index(s): s for s in chosen})
    if not df.empty:
        st.plotly_chart(charts.performance_chart(df, data.INDICES, f"{period}報酬率（起點 = 0%）"),
                        width="stretch")

# --- Watchlist snapshot -------------------------------------------------------
st.subheader("⭐ 自選股快覽")
rows = []
for t in load_watchlist():
    h = data.history(t, 200)
    if h.empty or len(h) < 61:
        continue
    ind = add_indicators(h)
    last = ind.iloc[-1]
    c = h["Close"]
    rows.append({
        "代碼": t,
        "收盤": round(float(last["Close"]), 2),
        "日漲跌": c.iloc[-1] / c.iloc[-2] - 1,
        "近 1 月": c.iloc[-1] / c.iloc[-22] - 1,
        "近 3 月": c.iloc[-1] / c.iloc[-61] - 1,
        "RSI": round(float(last["RSI14"]), 0),
        "站上季線": "✅" if last["Close"] > last["SMA60"] else "❌",
        "近 3 月走勢": c.iloc[-61:].tolist(),
    })
if rows:
    table = pd.DataFrame(rows)
    event = st.dataframe(
        table, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
        column_config={
            "日漲跌": st.column_config.NumberColumn(format="percent"),
            "近 1 月": st.column_config.NumberColumn(format="percent"),
            "近 3 月": st.column_config.NumberColumn(format="percent"),
            "近 3 月走勢": st.column_config.LineChartColumn(width="medium"),
        },
    )
    st.caption("點選一列會跳出完整走勢圖，也可以從那裡開啟個股分析。自選股可在左側欄編輯。")
    picked = table.iloc[event.selection.rows[0]]["代碼"] if event.selection.rows else None
    # Open once per new selection; later reruns (other widgets) must not reopen it.
    if picked and st.session_state.get("wl_dialog_for") != picked:
        st.session_state["wl_dialog_for"] = picked
        chart_dialog(picked)
    elif not picked:
        st.session_state.pop("wl_dialog_for", None)
else:
    st.info("自選股沒有可用資料。")

# --- Headlines ------------------------------------------------------------------
st.subheader("📰 市場頭條")
news = sorted(data.market_news("台股")[:5] + data.market_news("美股")[:5],
              key=lambda a: a.get("pub_date") or datetime(1970, 1, 1, tzinfo=timezone.utc), reverse=True)
for a in news[:8]:
    st.markdown(f"- [{a['title']}]({a['link']})　<span style='color:gray;font-size:0.85em'>"
                f"{a.get('publisher', '')} · {ago(a.get('pub_date'))}</span>", unsafe_allow_html=True)
st.page_link("views/news.py", label="看更多新聞與 AI 重點整理 →", icon="📰")
