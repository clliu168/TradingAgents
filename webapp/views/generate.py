from datetime import date, timedelta

import streamlit as st

from webapp import jobs
from webapp.ui import load_watchlist, normalize_ticker

st.title("🤖 產生報告")
st.caption("分析會在背景執行，關掉這個頁面也會繼續跑。每檔每種期間約 11 次 LLM 呼叫，會產生 API 費用。")

HORIZONS = {"both": "短線 + 中長期", "short": "短線", "long": "中長期"}
last_weekday = date.today() - timedelta(days=1)
while last_weekday.weekday() >= 5:
    last_weekday -= timedelta(days=1)

t1, t2 = st.tabs(["🎯 選股建議（自動挑股）", "🔍 指定個股分析"])

with t1, st.container(border=True):
    c1, c2, c3 = st.columns(3)
    horizon = c1.selectbox("投資期間", list(HORIZONS), format_func=HORIZONS.get)
    markets = c2.multiselect("市場", ["TW", "US"], default=["TW", "US"],
                             format_func={"TW": "台股", "US": "美股"}.get)
    top = c3.number_input("每個市場送入 AI 辯論的檔數", 1, 10, 2)
    d1, d2 = st.columns(2)
    as_of = d1.date_input("分析日期", last_weekday, max_value=date.today())
    screen_only = d2.toggle("只做量化篩選（不呼叫 LLM、免費、約 1–2 分鐘）", value=False)
    n_runs = 0 if screen_only else (2 if horizon == "both" else 1) * len(markets) * top
    st.caption(f"預計 AI 完整分析次數：{n_runs} 次" + ("" if screen_only else "（每次約數分鐘）"))
    if st.button("開始選股", type="primary", disabled=not markets):
        args = ["--horizon", horizon, "--markets", *markets, "--top", str(top), "--date", as_of.isoformat()]
        if screen_only:
            args.append("--screen-only")
        jobs.start("recommend", args, f"選股建議 {HORIZONS[horizon]}・{'/'.join(markets)}・前 {top} 檔"
                   + ("（僅篩選）" if screen_only else ""))
        st.success("已開始，進度在下方。")

with t2, st.form("watchlist"):
    wl = load_watchlist()
    chosen = st.multiselect("從自選股挑選", wl, default=wl[:1])
    extra = st.text_input("其他代碼（以空白或逗號分隔，如 2308 6488.TWO AAPL）")
    c1, c2 = st.columns(2)
    horizon2 = c1.selectbox("投資期間", list(HORIZONS), format_func=HORIZONS.get, key="h2")
    as_of2 = c2.date_input("分析日期", last_weekday, max_value=date.today(), key="d2")
    if st.form_submit_button("開始分析", type="primary"):
        tickers = list(dict.fromkeys(
            chosen + [normalize_ticker(x) for x in extra.replace(",", " ").split() if x.strip()]))
        if tickers:
            jobs.start("watchlist", [*tickers, "--horizon", horizon2, "--date", as_of2.isoformat()],
                       f"個股分析 {' '.join(tickers)}（{HORIZONS[horizon2]}）")
            st.success("已開始，進度在下方。")


@st.fragment(run_every=4)
def job_panel():
    st.subheader("工作進度")
    all_jobs = jobs.list_jobs()
    if not all_jobs:
        st.info("還沒有執行過的工作。")
        return
    for j in all_jobs[:10]:
        icon = {"執行中": "⏳", "完成": "✅"}.get(j["status"], "⚠️")
        with st.expander(f"{icon} {j['label']}　·　{j['started'][:16].replace('T', ' ')}　·　{j['status']}",
                         expanded=j["status"] == "執行中"):
            st.code(jobs.tail(j["dir"], 80) or "（等待輸出…）", language=None, height=280)
            c1, c2 = st.columns(2)
            if j["status"] == "執行中" and c1.button("停止", key=f"stop_{j['id']}"):
                jobs.stop(j["dir"])
                st.rerun()
            out = jobs.output_file(j["dir"]) if j["status"] != "執行中" else None
            if out and out.exists():
                c2.page_link("views/reports.py", label=f"查看報告：{out.name}", icon="📑")


job_panel()
