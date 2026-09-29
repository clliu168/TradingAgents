# 部署到伺服器（140.113.59.122）

部署完成後，這台伺服器會做兩件事：

- 24 小時跑著 Web 介面。介面只綁在伺服器本機的 127.0.0.1:8501，外部連不進來，您要從 Mac 用 SSH 通道連線。
- 每週二到週六早上 06:30（台北時間）自動更新一次，這時美股、台股前一個交易日都已收盤：
    1. **AI 選股**：台股、美股各取前 5 檔，短線、中長期各跑一次，共 20 次完整分析，大約需要 1–3 小時。
    2. **新聞摘要**：先把新聞頁三個分頁和自選股的新聞整理成摘要。

## 一、安裝（只需一次）

先登入伺服器：

```
ssh 您的帳號@140.113.59.122
```

下載安裝腳本並執行。過程中會用到 sudo 密碼，用來安裝 systemd 服務：

```
curl -fsSLO https://raw.githubusercontent.com/clliu168/TradingAgents/taiwan-horizon/deploy/install.sh
bash install.sh
```

安裝完填入 OpenAI key：

```
nano ~/TradingAgents/.env
```

找到 `OPENAI_API_KEY=` 這一行，把 key 貼在等號後面，然後按 Ctrl+O 存檔、Ctrl+X 離開。最後重新啟動網頁服務：

```
sudo systemctl restart tradingagents-web
```

如果想改變每天跑的檔數，在執行安裝腳本時指定 TOP。例如每組只跑 3 檔：

```
TOP=3 bash install.sh
```

## 二、從 Mac 打開網頁

在 Mac 的終端機執行下面這行，視窗保持開著：

```
ssh -N -L 8502:127.0.0.1:8501 您的帳號@140.113.59.122
```

然後用瀏覽器打開 http://localhost:8502 。本機這端用 8502，是為了避免跟您 Mac 上自己跑的 8501 衝突。

如果不想每次都打這麼長的指令，可以把下面這段加到 Mac 的 `~/.ssh/config`：

```
Host ta
    HostName 140.113.59.122
    User 您的帳號
    LocalForward 8502 127.0.0.1:8501
```

之後只要執行 `ssh -N ta`。

## 三、日常操作

伺服器上常用的指令：

| 要做的事 | 指令 |
| --- | --- |
| 看下次排程時間 | `systemctl list-timers tradingagents-daily.timer` |
| 立刻手動跑一次每日更新 | `sudo systemctl start tradingagents-daily` |
| 看每日更新的紀錄 | `journalctl -u tradingagents-daily -n 100` |
| 看網頁服務的紀錄 | `journalctl -u tradingagents-web -n 100` |
| 重新啟動網頁 | `sudo systemctl restart tradingagents-web` |
| 暫停每日排程 | `sudo systemctl disable --now tradingagents-daily.timer` |
| 更新程式碼（在 Mac 上 push 之後） | `bash ~/TradingAgents/deploy/install.sh` |

每日選股的進度和紀錄也會出現在網頁「產生報告」頁的工作列表裡，結果在「報告與建議」頁。

## 四、費用與注意事項

- **費用**：每天 20 次完整分析，每次大約 11 次 LLM 呼叫，另外加上新聞摘要。實際金額取決於您在 `.env` 選的模型，建議第一週每天到 OpenAI 後台看一下用量。
- **資料**：伺服器上的報告、自選股、新聞摘要快取放在 `~/TradingAgents/webapp_data`、`~/TradingAgents/recommendations` 和 `~/.tradingagents`。它們跟您 Mac 上的是兩份各自獨立的資料，不會同步。
- **key 的權限**：`.env` 的權限設成只有您的帳號能讀（600）。
- **不要把網頁開放到外網**：這個介面可以觸發會花錢的分析，也讀得到 key，所以請維持只聽 127.0.0.1、用 SSH 通道連線的做法。
- **性質**：輸出是研究參考，不是投資建議。
