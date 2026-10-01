from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from webapp import data
from webapp.performance import WINDOWS, evaluate, load_decisions, summarize
from webapp.ui import display_name, page_timestamp

st.title("🎯 AI 建議績效追蹤")
page_timestamp()
st.caption(
    "每一筆 AI 決策都從分析日收盤開始算：個股在之後 5／21／63 個交易日的報酬，減去同期間基準"
    "（台股上市：加權指數；上櫃：富櫃50 ETF；美股：SPY）的報酬，就是超額報酬。"
    "Buy／Overweight 超額報酬 > 0 算命中，Sell／Underweight < 0 算命中，Hold 不計分。"
)

decisions = load_decisions()
if decisions.empty:
    st.info("還沒有任何 AI 決策紀錄。每日排程或「產生報告」跑過之後，這裡就會開始累積。")
    st.stop()

span = (pd.Timestamp(date.today()) - decisions["date"].min()).days + 150
scored = evaluate(decisions, lambda s: data.history(s, span, warmup=0)["Close"])

window = st.radio("評估期間", WINDOWS, index=1, horizontal=True,
                  format_func=lambda n: {5: "5 個交易日（約 1 週）", 21: "21 個交易日（約 1 個月）",
                                         63: "63 個交易日（約 1 季）"}[n])
overall = summarize(scored, window)
k = st.columns(4)
k[0].metric("決策總數", len(scored))
if overall.empty:
    k[1].metric("已可評估", 0)
    st.info(f"還沒有決策滿 {window} 個交易日，暫時無法評估。短線建議約一週後、中長期建議約一季後才有結果。")
else:
    row = overall.iloc[0]
    k[1].metric("已可評估（非 Hold）", int(row["已評估筆數"]))
    k[2].metric("勝率", f"{row['勝率']:.0%}")
    k[3].metric("平均超額報酬（依方向）", f"{row['平均超額報酬（依方向）']:+.2%}")
    if row["已評估筆數"] < 30:
        st.warning(f"目前只有 {int(row['已評估筆數'])} 筆可評估，樣本太少，勝率和平均值的誤差都很大，先別據此下結論。")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### 依期間設定")
        st.dataframe(summarize(scored, window, by="horizon"), hide_index=True, width="stretch",
                     column_config={"勝率": st.column_config.NumberColumn(format="percent"),
                                    "平均超額報酬（依方向）": st.column_config.NumberColumn(format="percent"),
                                    "平均個股報酬": st.column_config.NumberColumn(format="percent")})
    with c2:
        st.markdown("##### 依評等")
        st.dataframe(summarize(scored, window, by="rating"), hide_index=True, width="stretch",
                     column_config={"勝率": st.column_config.NumberColumn(format="percent"),
                                    "平均超額報酬（依方向）": st.column_config.NumberColumn(format="percent"),
                                    "平均個股報酬": st.column_config.NumberColumn(format="percent")})

    done = scored[(scored["direction"] != 0) & scored[f"alpha_{window}"].notna()].copy()
    done["方向調整後超額報酬"] = done[f"alpha_{window}"].astype(float) * done["direction"]
    fig = px.histogram(done, x="方向調整後超額報酬", color="horizon", nbins=30, barmode="overlay",
                       labels={"horizon": "期間"}, title=f"每筆決策的超額報酬分布（{window} 日，> 0 表示判斷正確）")
    fig.add_vline(x=0, line_dash="dash", line_color="#64748b")
    fig.update_layout(xaxis_tickformat="+.0%", height=360, margin={"l": 10, "r": 10, "t": 50, "b": 10})
    st.plotly_chart(fig, width="stretch")

st.markdown("##### 所有決策")
show = scored[["date", "ticker", "horizon", "rating", "benchmark"]
              + [c for n in WINDOWS for c in (f"ret_{n}", f"alpha_{n}", f"hit_{n}")]].copy()
show["date"] = show["date"].dt.strftime("%Y-%m-%d")
names = {"date": "分析日", "ticker": "代碼", "horizon": "期間", "rating": "評等", "benchmark": "基準"}
for n in WINDOWS:
    names |= {f"ret_{n}": f"{n}日報酬", f"alpha_{n}": f"{n}日超額", f"hit_{n}": f"{n}日命中"}
show = show.rename(columns=names)
show.insert(2, "名稱", [display_name(t) for t in show["代碼"]])
pct_cols = [v for k_, v in names.items() if k_.startswith(("ret_", "alpha_"))]
st.dataframe(show, hide_index=True, width="stretch",
             column_config={c: st.column_config.NumberColumn(format="percent") for c in pct_cols})
st.caption("空白表示還沒滿該期間或抓不到價格。報酬不含股利與交易成本；AI 輸出僅供研究參考，不構成投資建議。")
