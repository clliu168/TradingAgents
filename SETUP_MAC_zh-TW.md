# 在 Mac 上執行（修改版 TradingAgents）

這個版本是基於官方 v0.5.1（commit 35543d0）修改而成，改動都放在 `taiwan-horizon` 分支。

## 修改內容

1. **台股基準**：`.TW` 的 alpha 改成對 `^TWII`（加權指數）計算，`.TWO` 改成對 `^TWOII`（櫃買指數）。原版會把台股都拿去跟 SPY 比。
2. **投資期間**：新增 `investment_horizon` 設定（`short` 或 `long`），會寫進每個 agent 的 prompt。結果的評估期間也跟著調整：短線 5 個交易日，中長期 63 個交易日（約一季）。
3. **`run_watchlist.py`**：一次跑多檔台股與美股、短線和中長期都跑，最後彙整成一份 summary。這支腳本還會：
    - 對台股額外搜尋台灣總經與產業新聞；
    - 預設用繁體中文輸出；
    - 讓短線和中長期各用一份決策紀錄，避免反思時把兩種期間混在一起。
4. **測試**：新增 `tests/test_taiwan_horizon.py`，全部 1008 個測試都通過。

## 第一次安裝

在「終端機」App 裡執行：

```bash
cd ~/Projects/TradingAgents
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
cp .env.example .env
open -e .env        # 填入 OPENAI_API_KEY=sk-...，存檔
```

`.env` 裡建議另外加上這兩行：

```
SEC_EDGAR_USER_AGENT=Your Name your@email.com
TRADINGAGENTS_OUTPUT_LANGUAGE=Traditional Chinese
```

如果有 FRED 的免費 key，也可以一併填進去，總經資料會比較完整。

## 執行

```bash
cd ~/Projects/TradingAgents
source .venv/bin/activate
python run_watchlist.py 2330.TW 2454.TW 2317.TW NVDA MSFT GOOGL --horizon both
```

- 每一檔、每一種期間大約要 11 次 LLM 呼叫加上 20 多次工具呼叫，6 檔 × 2 種期間總共 12 次分析，會需要一段時間，也會產生 API 費用。第一次建議先跑 1 檔試試看。
- 彙整結果寫在 `watchlist_results/summary_*.md`，完整報告寫在 `~/.tradingagents/logs/`。

## 選股建議（短線／中長期）

```bash
python recommend.py --screen-only      # 只跑量化篩選，不花 LLM 費用，約 1–2 分鐘
python recommend.py                    # 篩選 + 多 agent 辯論，兩種期間、台美股各取前 3 檔
python recommend.py --top 2 --horizon long --markets TW
```

流程分兩個階段：

1. **量化篩選**（`tradingagents/screener.py`）：從股票池裡挑出候選股。台股約 55 檔（接近 0050 成分股，加上幾檔上櫃龍頭），美股 60 檔大型股，清單可以直接修改。
    - 短線看近 20／60 日動能、均線多頭排列、量能放大，以及 RSI 是否過熱。
    - 中長期看 12-1 月動能、是否站上 200 日線、ROE、營收與獲利成長、淨利率、負債比和預估本益比。
    - 分數只在同一個市場內比較。
2. **多 agent 辯論**：用對應的期間設定，跑完整的 TradingAgents 流程。最終評等是 Buy 或 Overweight 的才列入建議，其餘候選股會附上未入選的原因。

結果寫在 `recommendations/recommendations_*.md`，每檔都附有量化篩選理由、行動方案和投資論點。預設跑 12 次完整分析（2 種期間 × 2 個市場 × 3 檔），費用和時間都比較高，可以用 `--top` 或 `--markets` 縮小範圍。

注意：基本面欄位取的是 Yahoo 目前的資料，不是當時的資料，所以只適合用在「今天」的分析，不能拿來做歷史回測。

## 已知限制

- 台股的新聞和社群情緒來源（Yahoo、StockTwits、Reddit）大多是英文，資料明顯比美股少。
- SEC EDGAR 的財報和 FRED 的總經資料都只涵蓋美國。
- LLM 的輸出不具決定性：同一天重跑一次，結果可能不一樣。
- 輸出只是研究參考，不是投資建議。
