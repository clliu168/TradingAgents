import pandas as pd
import plotly.express as px
import streamlit as st

from webapp import alerts, notify, usage
from webapp.ui import load_watchlist, page_timestamp

st.title("⚙️ 設定與費用")
page_timestamp()

tab_cost, tab_notify, tab_alert = st.tabs(["💰 API 費用與預算", "🔔 通知管道", "🚨 警示規則"])

# --- Cost ---------------------------------------------------------------------------------
with tab_cost:
    df = usage.load()
    s = usage.spend(df)
    b = usage.budget()
    k = st.columns(4)
    k[0].metric("今天", f"${s['today']:.2f}", f"上限 ${b['daily_usd']:.0f}" if b["daily_usd"] else "不設上限",
                delta_color="off")
    k[1].metric("本月", f"${s['month']:.2f}", f"上限 ${b['monthly_usd']:.0f}" if b["monthly_usd"] else "不設上限",
                delta_color="off")
    k[2].metric("近 30 天", f"${s['last30']:.2f}")
    k[3].metric("LLM 呼叫次數（累計）", f"{len(df):,}")
    blocked, why = usage.over_budget()
    if blocked:
        st.error(f"🚫 {why}：每日排程、AI 分析按鈕與新聞摘要已暫停，直到明天或下個月，或調高上限。")

    if not df.empty:
        if (~df["priced"]).any():
            st.warning("有些模型不在單價表中，這些呼叫的費用暫以 0 計算：" + "、".join(sorted(df.loc[~df["priced"], "model"].unique())))
        d = df.copy()
        d["日期"] = d["ts"].dt.tz_convert(usage.TZ).dt.date if d["ts"].dt.tz is not None else d["ts"].dt.date
        d["用途"] = d["source"].str.split(":").str[0].map(
            {"recommend": "每日/手動選股", "watchlist": "個股分析", "news-summary": "新聞摘要", "news-digest": "新聞總整理"}
        ).fillna(d["source"])
        daily = d.groupby(["日期", "用途"], as_index=False)["cost_usd"].sum()
        daily["日期"] = daily["日期"].astype(str)
        fig = px.bar(daily, x="日期", y="cost_usd", color="用途", title="每日 API 費用（美元）",
                     labels={"cost_usd": "美元"})
        fig.update_layout(height=340, margin={"l": 10, "r": 10, "t": 50, "b": 10}, xaxis_type="category")
        st.plotly_chart(fig, width="stretch")
        by_model = d.groupby("model", as_index=False)[["input", "output", "cost_usd"]].sum()
        st.dataframe(by_model.rename(columns={"model": "模型", "input": "輸入 tokens", "output": "輸出 tokens",
                                              "cost_usd": "費用（美元）"}),
                     hide_index=True, width="stretch",
                     column_config={"費用（美元）": st.column_config.NumberColumn(format="$%.2f")})
    else:
        st.info("還沒有 LLM 使用紀錄。")

    st.markdown("##### 預算上限")
    st.caption("達到上限後，每日排程會跳過 AI 選股與新聞摘要並發通知，網頁上的 AI 按鈕也會停用。填 0 表示不設上限。")
    c1, c2 = st.columns(2)
    daily_cap = c1.number_input("每日上限（美元）", 0.0, 1000.0, float(b["daily_usd"]), 1.0)
    month_cap = c2.number_input("每月上限（美元）", 0.0, 10000.0, float(b["monthly_usd"]), 10.0)
    st.markdown("##### 模型單價（美元 / 每百萬 tokens）")
    st.caption("預設值來自 OpenAI 官方價目表（2026-09 查詢）。改用其他模型或價格變動時請在這裡更新。")
    ptab = pd.DataFrame([{"模型": m, "輸入": v[0], "快取輸入": v[1], "輸出": v[2]} for m, v in usage.prices().items()])
    ptab = st.data_editor(ptab, num_rows="dynamic", hide_index=True, width="stretch", key="price_editor")
    if st.button("💾 儲存預算與單價", type="primary"):
        usage.save_budget({"daily_usd": daily_cap, "monthly_usd": month_cap})
        usage.save_prices({str(r["模型"]).strip().lower(): [float(r["輸入"] or 0), float(r["快取輸入"] or 0),
                                                           float(r["輸出"] or 0)]
                           for _, r in ptab.dropna(subset=["模型"]).iterrows() if str(r["模型"]).strip()})
        st.success("已儲存")
        st.rerun()

# --- Notification channels ------------------------------------------------------------------
with tab_notify:
    ch = notify.channels()
    st.markdown(f"目前已設定的通知管道：**{'、'.join(ch) if ch else '無'}**")
    st.markdown("""
通知管道的帳號密碼寫在伺服器的 `.env`，不透過網頁設定（避免密碼存在網頁可讀的地方）。在 `.env` 加上其中一組或兩組：

**Telegram**（建議，免費、手機即時收到）：
1. 在 Telegram 找 **@BotFather**，傳 `/newbot`，照指示取名後拿到 bot token。
2. 對你的新 bot 隨便傳一句話，再用瀏覽器打開 `https://api.telegram.org/bot<token>/getUpdates`，找到 `"chat":{"id":...}` 那串數字。
""")
    st.code("TELEGRAM_BOT_TOKEN=123456:ABC...\nTELEGRAM_CHAT_ID=123456789", language=None)
    st.markdown("**Email**（Gmail 需使用「應用程式密碼」，不是登入密碼）：")
    st.code("SMTP_HOST=smtp.gmail.com\nSMTP_PORT=587\nSMTP_USER=you@gmail.com\nSMTP_PASSWORD=應用程式密碼\n"
            "NOTIFY_EMAIL_TO=you@gmail.com", language=None)
    st.caption("改完 .env 後執行 sudo systemctl restart tradingagents-web 讓網頁讀到新設定。")
    if st.button("📨 傳送測試通知", disabled=not ch):
        ok = notify.send("✅ TradingAgents 測試通知：設定成功。")
        (st.success if ok else st.error)(f"已送出：{'、'.join(ok)}" if ok else "傳送失敗，請看伺服器紀錄。")

# --- Alert rules -------------------------------------------------------------------------------
with tab_alert:
    r = alerts.load_rules()
    st.caption("警示會檢查自選股與持股，在台股收盤後（14:10）與美股收盤後（每日更新時）各檢查一次，同一個訊號同一天只通知一次。")
    enabled = st.toggle("啟用警示", value=r["enabled"])
    c1, c2, c3 = st.columns(3)
    sma60 = c1.checkbox("站上／跌破季線（60 日）", value=r["sma60_cross"])
    sma240 = c1.checkbox("站上／跌破年線（240 日）", value=r["sma240_cross"])
    reb = c1.checkbox("持股偏離目標比例", value=r["rebalance"])
    rsi_hi = c2.number_input("RSI 高於（0 = 關閉）", 0, 100, int(r["rsi_high"]))
    rsi_lo = c2.number_input("RSI 低於（0 = 關閉）", 0, 100, int(r["rsi_low"]))
    move = c3.number_input("單日漲跌超過 %（0 = 關閉）", 0.0, 50.0, float(r["daily_move_pct"]), 0.5)
    st.markdown("##### 價格目標")
    targets = pd.DataFrame(r["price_targets"] or [], columns=["ticker", "above", "below"])
    targets = st.data_editor(targets, num_rows="dynamic", hide_index=True, width="stretch", key="target_editor",
                             column_config={"ticker": st.column_config.TextColumn("代碼"),
                                            "above": st.column_config.NumberColumn("漲到以上"),
                                            "below": st.column_config.NumberColumn("跌到以下")})
    b1, b2 = st.columns(2)
    if b1.button("💾 儲存警示規則", type="primary"):
        alerts.save_rules({
            "enabled": enabled, "sma60_cross": sma60, "sma240_cross": sma240, "rebalance": reb,
            "rsi_high": rsi_hi, "rsi_low": rsi_lo, "daily_move_pct": move,
            "price_targets": [{"ticker": str(t["ticker"]).strip().upper(),
                               "above": None if pd.isna(t["above"]) else float(t["above"]),
                               "below": None if pd.isna(t["below"]) else float(t["below"])}
                              for _, t in targets.dropna(subset=["ticker"]).iterrows()],
        })
        st.success("已儲存")
    if b2.button("🔍 現在檢查一次（只顯示，不發通知）"):
        from webapp import data

        with st.spinner("檢查中…"):
            fired = alerts.run(lambda t: data.history(t, 400), load_watchlist(), dry_run=True)
        st.write("\n".join(f"- {f}" for f in fired) if fired else "目前沒有觸發任何警示。")
