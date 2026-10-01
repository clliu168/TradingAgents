import pandas as pd
import streamlit as st

from tradingagents.screener import long_reason, price_features, short_reason
from webapp import charts, cnnews, data, jobs, twdata
from webapp.indicators import add_indicators, signals
from webapp.services import RESULTS_DIR
from webapp.ui import (
    ai_digest_block,
    display_name,
    fmt_bar_date,
    fmt_num,
    fmt_pct,
    load_watchlist,
    news_list,
    normalize_ticker,
)

st.title("📊 個股分析")

# --- Ticker selection -------------------------------------------------------------
wl = load_watchlist()
default = st.session_state.get("stock_ticker", wl[0] if wl else "2330.TW")
c1, c2, c3 = st.columns([2, 2, 1])
typed = c1.text_input("股票代碼（台股可只打代號，如 2330；上櫃請加 .TWO）", value=default)
picked = c2.selectbox("或從自選股選擇", ["—"] + wl, index=0)
period = c3.selectbox("期間", list(data.PERIOD_DAYS), index=3)
ticker = normalize_ticker(picked if picked != "—" else typed)
st.session_state["stock_ticker"] = ticker

hist = data.history(ticker, data.PERIOD_DAYS[period])
if hist.empty or len(hist) < 30:
    st.error(f"抓不到 {ticker} 的股價。台股上市請用 .TW、上櫃用 .TWO（例如 6488.TWO）。")
    st.stop()

ind = add_indicators(hist)
cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=data.PERIOD_DAYS[period])
view = ind[ind.index >= cutoff]
info = data.profile(ticker)
name = display_name(ticker) or info.get("longName") or ticker
last, prev = hist["Close"].iloc[-1], hist["Close"].iloc[-2]

st.subheader(f"{name}（{ticker}）")
st.caption(f"📅 最新資料：{fmt_bar_date(hist.index[-1])}，漲跌比較 {hist.index[-2]:%Y-%m-%d}　"
           f"｜ 期間：{view.index[0]:%Y-%m-%d} ～ {view.index[-1]:%Y-%m-%d}")
m = st.columns(6)
m[0].metric("收盤", f"{last:,.2f}", fmt_pct(last / prev - 1), delta_color="inverse")
m[1].metric("期間漲跌", fmt_pct(view["Close"].iloc[-1] / view["Close"].iloc[0] - 1))
m[2].metric("52 週區間", f"{hist['Low'].iloc[-252:].min():,.0f}–{hist['High'].iloc[-252:].max():,.0f}")
m[3].metric("市值", fmt_num(info.get("marketCap"), 1))
m[4].metric("本益比（近四季）", fmt_num(info.get("trailingPE"), 1))
m[5].metric("殖利率", f"{info['dividendYield']:.2f}%" if info.get("dividendYield") else "—")

tab_chart, tab_fund, tab_chip, tab_news, tab_ai = st.tabs(
    ["📈 走勢與技術分析", "🏢 基本面", "🏦 籌碼與營收", "📰 新聞", "🤖 AI 分析"])

with tab_chart:
    o1, o2, o3 = st.columns([3, 1, 3])
    mas = o1.multiselect("均線", ["SMA5", "SMA20", "SMA60", "SMA120", "SMA240"], default=["SMA20", "SMA60", "SMA240"],
                         format_func=lambda s: s.replace("SMA", "MA"))
    boll = o2.toggle("布林通道", value=False)
    lower = o3.multiselect("副圖指標", ["MACD", "RSI", "KD"], default=["MACD", "RSI"])
    st.plotly_chart(charts.price_chart(view, f"{ticker} 日 K 線", mas, boll, lower), width="stretch")

    st.markdown("##### 技術面訊號")
    tone_icon = {"good": "🔴", "bad": "🟢", "neutral": "⚪"}
    cols = st.columns(2)
    for i, (tone, text) in enumerate(signals(ind)):
        cols[i % 2].markdown(f"{tone_icon[tone]} {text}")
    st.caption("🔴 偏多　🟢 偏空　⚪ 中性（台股慣例：紅漲綠跌）。訊號只描述目前型態，不代表未來走勢。")

    feats = price_features(hist[["Close", "Volume"]])
    if feats:
        fund_fields = ("returnOnEquity", "revenueGrowth", "earningsGrowth", "profitMargins", "forwardPE")
        row = pd.Series({**feats, **{k: pd.to_numeric(info.get(k), errors="coerce") for k in fund_fields}})
        st.markdown("##### 選股模型的讀法")
        st.markdown(f"**短線**：{short_reason(row)}")
        st.markdown(f"**中長期**：{long_reason(row)}")

with tab_fund:
    f1, f2 = st.columns(2)
    fund = [
        ("預估本益比", fmt_num(info.get("forwardPE"), 1)), ("股價淨值比", fmt_num(info.get("priceToBook"), 2)),
        ("ROE", fmt_pct(info.get("returnOnEquity"), 1)), ("淨利率", fmt_pct(info.get("profitMargins"), 1)),
        ("營收成長（年增）", fmt_pct(info.get("revenueGrowth"), 1)),
        ("獲利成長（年增）", fmt_pct(info.get("earningsGrowth"), 1)),
        ("負債權益比", fmt_num(info.get("debtToEquity"), 1)), ("Beta", fmt_num(info.get("beta"), 2)),
    ]
    f1.dataframe(pd.DataFrame(fund, columns=["指標", "數值"]), hide_index=True, width="stretch")
    f2.markdown(f"**產業**：{info.get('sector', '—')} / {info.get('industry', '—')}")
    f2.markdown(f"**國家**：{info.get('country', '—')}　**幣別**：{info.get('currency', '—')}")
    if info.get("website"):
        f2.markdown(f"**網站**：{info['website']}")
    if info.get("longBusinessSummary"):
        with f2.expander("公司簡介", expanded=True):
            st.write(info["longBusinessSummary"])
    st.caption("基本面為 Yahoo Finance 目前的數值；台股部分欄位可能缺漏。")

with tab_chip:
    sid = twdata.stock_id(ticker)
    if not sid:
        st.info("籌碼（三大法人、融資融券）與月營收只提供台股。美股可看「基本面」分頁。")
    else:
        try:
            flows = twdata.institutional_flows(sid, 60)
            mg = twdata.margin(sid, 120)
            rev = twdata.month_revenue(sid, 26)
            divs = twdata.dividends(sid)
        except Exception as exc:  # noqa: BLE001
            st.error(f"FinMind 資料抓取失敗：{exc}")
            st.caption("請確認伺服器 .env 有 FINMIND_TOKEN（到 finmindtrade.com 免費註冊取得），並重新啟動網頁服務。")
            flows = mg = rev = divs = pd.DataFrame()
        if not flows.empty:
            last5, last20 = flows.tail(5).sum(), flows.tail(20).sum()
            k = st.columns(4)
            for i, g in enumerate(["外資", "投信", "自營商", "合計"]):
                if g in flows:
                    k[i].metric(f"{g} 近 5 日", f"{last5[g]:+,.0f} 張", f"近 20 日 {last20[g]:+,.0f} 張",
                                delta_color="off")
            st.plotly_chart(charts.flows_chart(flows), width="stretch")
            st.caption(f"資料日期：{flows.index[0]:%Y-%m-%d} ～ {flows.index[-1]:%Y-%m-%d}；單位：張（1 張 = 1,000 股），正值為買超。")
        if not mg.empty:
            st.plotly_chart(charts.margin_chart(mg), width="stretch")
        if not rev.empty:
            last = rev.iloc[-1]
            k = st.columns(3)
            k[0].metric(f"{rev.index[-1]:%Y 年 %m 月}營收", f"{last['營收（億）']:,.1f} 億")
            k[1].metric("年增率", f"{last['年增率']:+.1%}" if pd.notna(last["年增率"]) else "—")
            k[2].metric("月增率", f"{last['月增率']:+.1%}" if pd.notna(last["月增率"]) else "—")
            st.plotly_chart(charts.revenue_chart(rev), width="stretch")
            st.caption(f"最新一期於 {last['公布日']:%Y-%m-%d} 公布。")
        if not divs.empty:
            st.markdown("##### 股利與除權息")
            st.dataframe(divs.head(6), hide_index=True, width="stretch")
        if not flows.empty or not rev.empty:
            st.caption("資料來源：FinMind（整理自證交所、櫃買中心、公開資訊觀測站）。")

with tab_news:
    lang = st.radio("來源", ["全部", "中文", "英文"], horizontal=True, key="stock_news_lang")
    zh = cnnews.stock_news(ticker) if lang != "英文" else []
    en = data.ticker_news(ticker) if lang != "中文" else []
    articles = data._sorted_unique(zh + en)
    ai_digest_block(articles, f"{name}（{ticker}）", key=f"stock_{ticker}_{lang}")
    news_list(articles, limit=20, key=f"stock_{ticker}_{lang}")

with tab_ai:
    reports = sorted((RESULTS_DIR / "reports").glob(f"{ticker}_*/complete_report.md"), reverse=True) \
        if (RESULTS_DIR / "reports").exists() else []
    a1, a2 = st.columns([2, 1])
    horizon = a2.radio("期間", ["short", "long", "both"], horizontal=True,
                       format_func={"short": "短線", "long": "中長期", "both": "兩者"}.get)
    if a2.button(f"🚀 用 AI 團隊分析 {ticker}", type="primary", width="stretch"):
        jobs.start("watchlist", [ticker, "--horizon", horizon], f"{ticker} 個股分析（{horizon}）")
        st.success("已在背景開始分析，約需數分鐘。可到「產生報告」頁看進度。")
    if reports:
        pick = a1.selectbox("歷次報告", reports, format_func=lambda p: p.parent.name.replace(f"{ticker}_", ""))
        with st.container(border=True):
            st.markdown(pick.read_text(encoding="utf-8"))
    else:
        a1.info("這檔股票還沒有 AI 分析報告。按右邊的按鈕產生一份。")
