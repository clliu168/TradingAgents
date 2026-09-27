import pandas as pd
import streamlit as st

from webapp.services import list_reports, parse_recommendations, split_report_sections
from webapp.ui import open_stock

st.title("📑 報告與建議")

reports = list_reports()
recs = [r for r in reports if r.kind == "選股建議"]

# --- Latest suggestions --------------------------------------------------------------
st.subheader("最新建議個股")
if recs:
    latest = recs[0]
    text = latest.path.read_text(encoding="utf-8")
    rows = parse_recommendations(text)
    st.caption(f"來源：{latest.title}（{latest.modified:%Y-%m-%d %H:%M}）")
    if rows:
        table = pd.DataFrame(rows)
        event = st.dataframe(table, hide_index=True, width="stretch",
                             on_select="rerun", selection_mode="single-row")
        sections = split_report_sections(text)
        if event.selection.rows:
            t = table.iloc[event.selection.rows[0]]["代碼"]
            with st.container(border=True):
                st.markdown(f"#### {t} 的建議理由")
                st.markdown(sections.get(t, "（報告中沒有這檔的詳細段落）"))
                if st.button(f"📊 開啟 {t} 個股分析"):
                    open_stock(t)
        else:
            st.caption("點選一列查看建議理由。")
    else:
        st.info("最新一份選股報告裡沒有通過辯論的建議個股（可能是「只做篩選」或全部未通過）。下方可查看全文。")
else:
    st.info("還沒有選股報告。到「產生報告」頁開始第一次選股。")
    st.page_link("views/generate.py", label="前往產生報告", icon="🤖")

# --- All reports ------------------------------------------------------------------------
st.subheader("所有報告")
if not reports:
    st.stop()
kinds = st.multiselect("類型", ["選股建議", "個股彙整", "完整報告"], default=["選股建議", "個股彙整", "完整報告"])
shown = [r for r in reports if r.kind in kinds]
if not shown:
    st.stop()
pick = st.selectbox("選擇報告", shown,
                    format_func=lambda r: f"[{r.kind}] {r.title}　{r.modified:%Y-%m-%d %H:%M}")
body = pick.path.read_text(encoding="utf-8")
st.download_button("下載 Markdown", body, file_name=pick.path.name, mime="text/markdown")
with st.container(border=True):
    st.markdown(body)
