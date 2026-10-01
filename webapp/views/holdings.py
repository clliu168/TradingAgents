import pandas as pd
import plotly.express as px
import streamlit as st

from webapp import data, portfolio as pfm
from webapp.ui import display_name, fmt_num, page_timestamp

st.title("💼 我的持倉")
page_timestamp()
st.caption("持股只存在這台機器的 webapp_data/portfolio.json，不會上傳。台股以台幣、美股以美元計價，總覽換算成台幣。")


def last_price(t: str) -> float | None:
    h = data.history(t, 10, warmup=0)
    return float(h["Close"].iloc[-1]) if not h.empty else None


pf = pfm.load()
fx_hist = data.history("TWD=X", 10, warmup=0)
usd_twd = float(fx_hist["Close"].iloc[-1]) if not fx_hist.empty else 32.0

with st.expander("✏️ 編輯持股", expanded=not pf["positions"]):
    st.caption("代碼：台股加 .TW（上市）或 .TWO（上櫃），例如 006208.TW；美股直接打代碼，例如 VTI。"
               "目標比例（%）可留空；有填的會用來提醒再平衡。")
    base = pd.DataFrame(pf["positions"] or [{"ticker": "006208.TW", "shares": 0, "cost": 0, "target": None}],
                        columns=["ticker", "shares", "cost", "target"])
    # Start every numeric column as float; an all-integer column makes the editor reject decimals.
    base[["shares", "cost", "target"]] = base[["shares", "cost", "target"]].astype(float)
    edited = st.data_editor(
        base, num_rows="dynamic", width="stretch", key="pf_editor",
        column_config={
            "ticker": st.column_config.TextColumn("代碼", required=True),
            "shares": st.column_config.NumberColumn("股數", min_value=0, step=0.0001),
            "cost": st.column_config.NumberColumn("平均成本（原幣／每股）", min_value=0, step=0.0001),
            "target": st.column_config.NumberColumn("目標比例 %", min_value=0, max_value=100, step=0.1),
        },
    )
    c1, c2, c3 = st.columns(3)
    cash_twd = c1.number_input("台幣現金", min_value=0.0, value=float(pf["cash_twd"]), step=10000.0)
    cash_usd = c2.number_input("美元現金", min_value=0.0, value=float(pf["cash_usd"]), step=100.0)
    band = c3.number_input("再平衡容許偏離（百分點）", min_value=1.0, max_value=30.0,
                           value=float(pf["rebalance_band"]) * 100, step=1.0)
    if st.button("💾 儲存持股", type="primary"):
        rows = edited.dropna(subset=["ticker"]).to_dict("records")
        for r in rows:
            r["ticker"] = str(r["ticker"]).strip().upper()
            for k in ("shares", "cost", "target"):  # blank cells come back as NaN; store them as null
                if pd.isna(r.get(k)):
                    r[k] = None
        pfm.save({"cash_twd": cash_twd, "cash_usd": cash_usd, "rebalance_band": band / 100,
                  "positions": [r for r in rows if r["ticker"]]})
        st.success("已儲存")
        st.rerun()

if not pf["positions"]:
    st.info("先在上方輸入持股並儲存。")
    st.stop()

df = pfm.valuate(pf, last_price, usd_twd)
df.insert(1, "名稱", [display_name(t) if not str(t).startswith("現金") else "" for t in df["代碼"]])
total = df["市值（台幣）"].fillna(0).sum()
stocks = df[~df["代碼"].str.startswith("現金")]
cost_twd = sum(r["成本價"] * r["股數"] * (usd_twd if r["幣別"] == "USD" else 1)
               for _, r in stocks.iterrows() if r["成本價"])
value_twd = stocks["市值（台幣）"].fillna(0).sum()
k = st.columns(4)
k[0].metric("總資產（台幣）", fmt_num(total, 0))
k[1].metric("持股市值", fmt_num(value_twd, 0))
k[2].metric("未實現損益", fmt_num(value_twd - cost_twd, 0),
            f"{value_twd / cost_twd - 1:+.2%}" if cost_twd else None, delta_color="inverse")
k[3].metric("美元/台幣", f"{usd_twd:.3f}")

c1, c2 = st.columns([3, 2])
with c1:
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        c: st.column_config.NumberColumn(format="percent") for c in ("報酬率", "目標比例", "目前比例", "偏離")
    } | {c: st.column_config.NumberColumn(format="%,.0f") for c in ("市值（原幣）", "市值（台幣）", "損益（原幣）")}
      | {c: st.column_config.NumberColumn(format="%.2f") for c in ("成本價", "現價")})
with c2:
    fig = px.pie(df, names="代碼", values="市值（台幣）", hole=0.5, title="目前配置（依台幣市值）")
    fig.update_layout(height=320, margin={"l": 10, "r": 10, "t": 50, "b": 10})
    st.plotly_chart(fig, width="stretch")

st.subheader("⚖️ 再平衡檢查")
rb = pfm.rebalance(df, pf["rebalance_band"], usd_twd)
if df["目標比例"].fillna(0).sum() == 0:
    st.info("還沒設定目標比例，所以不做再平衡檢查。")
elif rb.empty:
    st.success(f"所有持股都在目標比例 ±{pf['rebalance_band']:.0%} 之內，不需要調整。")
else:
    st.warning(f"以下持股偏離目標超過 ±{pf['rebalance_band']:.0%}：")
    st.dataframe(rb, hide_index=True, width="stretch", column_config={
        c: st.column_config.NumberColumn(format="percent") for c in ("目前比例", "目標比例", "偏離")
    } | {"調整金額（台幣）": st.column_config.NumberColumn(format="%,.0f")})
    st.caption("股數依現價估算，未含手續費、稅與零股規則，實際下單前請自行確認。")

st.subheader("🤖 讓 AI 分析考慮持股")
st.caption("在「產生報告」頁勾選「帶入我的持倉」，交易員、風控與投資組合經理 agent 就會知道您已持有哪些部位與成本；"
           "每日自動選股也會自動帶入。")
