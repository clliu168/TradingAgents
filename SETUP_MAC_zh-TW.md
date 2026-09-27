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

## 已知限制

- 台股的新聞和社群情緒來源（Yahoo、StockTwits、Reddit）大多是英文，資料明顯比美股少。
- SEC EDGAR 的財報和 FRED 的總經資料都只涵蓋美國。
- LLM 的輸出不具決定性：同一天重跑一次，結果可能不一樣。
- 輸出只是研究參考，不是投資建議。
