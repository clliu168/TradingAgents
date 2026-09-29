import numpy as np
import pandas as pd
import streamlit as st

from webapp import charts, data
from webapp.ui import load_watchlist, normalize_ticker, page_timestamp

st.title("⚖️ 多檔比較")
page_timestamp()

wl = load_watchlist()
c1, c2, c3 = st.columns([3, 2, 1])
chosen = c1.multiselect("從自選股挑選", wl, default=wl[:4])
extra = c2.text_input("其他代碼（空白分隔，例如 006208 VTI VT）")
period = c3.selectbox("期間", list(data.PERIOD_DAYS), index=3)
tickers = list(dict.fromkeys(chosen + [normalize_ticker(x) for x in extra.split() if x.strip()]))
if len(tickers) < 2:
    st.info("至少選兩檔來比較。")
    st.stop()

closes = data.closes(tuple(tickers), data.PERIOD_DAYS[period])
missing = [t for t in tickers if t not in closes.columns]
if missing:
    st.warning("抓不到資料：" + "、".join(missing))
if closes.shape[1] < 2:
    st.stop()

st.plotly_chart(charts.performance_chart(closes, {}, f"{period}報酬率（起點 = 0%，各自以原幣計）"), width="stretch")

rets = closes.pct_change()
stats = []
for t in closes.columns:
    s = closes[t].dropna()
    r = rets[t].dropna()
    dd = (s / s.cummax() - 1).min()
    vol = r.std() * np.sqrt(252)
    ann = (s.iloc[-1] / s.iloc[0]) ** (252 / max(len(s) - 1, 1)) - 1
    stats.append({"代碼": t, "期間報酬": s.iloc[-1] / s.iloc[0] - 1, "年化報酬": ann, "年化波動": vol,
                  "最大回撤": dd, "報酬／波動": ann / vol if vol else None,
                  "起": f"{s.index[0]:%Y-%m-%d}", "迄": f"{s.index[-1]:%Y-%m-%d}"})
st.dataframe(pd.DataFrame(stats), hide_index=True, width="stretch", column_config={
    c: st.column_config.NumberColumn(format="percent") for c in ("期間報酬", "年化報酬", "年化波動", "最大回撤")
} | {"報酬／波動": st.column_config.NumberColumn(format="%.2f")})

# Weekly returns avoid the one-day offset between Taipei and New York closes.
weekly = closes.resample("W-FRI").last().pct_change().dropna(how="all")
corr = weekly.corr()
st.plotly_chart(charts.correlation_heatmap(corr), width="stretch")
st.caption("相關係數用「週報酬」計算：台股與美股收盤時間差約半天，用日報酬會低估兩者的連動。"
           "數值越接近 1 表示走勢越同步、分散效果越小。報酬以各自幣別計算，未含股利與匯率變動。")
