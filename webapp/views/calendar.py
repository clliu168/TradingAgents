from datetime import date, timedelta

import pandas as pd
import streamlit as st

from webapp import calendar_data as cal, portfolio as pfm
from webapp.ui import load_watchlist, page_timestamp

st.title("📅 行事曆")
page_timestamp()

days = st.slider("往後看幾天", 7, 120, 45)
today = date.today()
end = today + timedelta(days=days)

rows = []
for e in cal.macro_events():
    d = date.fromisoformat(e["date"])
    if today <= d <= end:
        tpe = cal.to_taipei(e["date"], e.get("time_et"))
        rows.append({"日期": d, "台北時間": f"{tpe:%m/%d %H:%M}" if tpe else "", "類別": "總經",
                     "代碼": "", "事件": e["event"], "來源": e.get("source", "")})
tickers = list(dict.fromkeys(load_watchlist() + [p["ticker"] for p in pfm.load().get("positions", [])]))
with st.spinner("讀取個股行事曆…"):
    for t in tickers:
        for e in cal.company_events(t):
            if today <= e["date"] <= end:
                rows.append({"日期": e["date"], "台北時間": "", "類別": "個股", "代碼": t, "事件": e["event"],
                             "來源": "FinMind" if t.endswith((".TW", ".TWO")) and "除" in e["event"] else "Yahoo"})

if not rows:
    st.info("這段期間沒有已知事件。")
else:
    df = pd.DataFrame(rows).sort_values(["日期", "台北時間"]).drop_duplicates(["日期", "代碼", "事件"])
    df["星期"] = df["日期"].map(lambda d: "一二三四五六日"[d.weekday()])
    df["倒數"] = df["日期"].map(lambda d: "今天" if d == today else f"{(d - today).days} 天後")
    kinds = st.multiselect("類別", ["總經", "個股"], default=["總經", "個股"])
    st.dataframe(df[df["類別"].isin(kinds)][["日期", "星期", "倒數", "台北時間", "類別", "代碼", "事件", "來源"]],
                 hide_index=True, width="stretch")
st.caption("個股事件涵蓋自選股與持股。美股財報日期是 Yahoo 的預估值，公司正式公告前可能變動；"
           "台股除權息資料需要 FINMIND_TOKEN。總經事件的美東時間已換算成台北時間。")

with st.expander("✏️ 編輯總經事件"):
    st.caption("預設清單已於 2026-09-29 對照聯準會與美國勞工統計局官網；之後的日期請自行補上。")
    edited = st.data_editor(pd.DataFrame(cal.macro_events(), columns=["date", "time_et", "event", "source"]),
                            num_rows="dynamic", hide_index=True, width="stretch", key="macro_editor",
                            column_config={"date": "日期（YYYY-MM-DD）", "time_et": "美東時間（HH:MM）",
                                           "event": "事件", "source": "來源"})
    if st.button("💾 儲存總經事件"):
        cal.save_macro([{k: ("" if pd.isna(v) else str(v)) for k, v in r.items()}
                        for r in edited.dropna(subset=["date"]).to_dict("records")])
        st.success("已儲存")
        st.rerun()
