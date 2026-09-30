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

## 二、打開網頁

有三種方式，可以同時使用。網頁本身永遠只聽 127.0.0.1，外面只能經由下面其中一種方式進來。

### A. Tailscale（建議，平常使用）

伺服器、Mac、手機各裝一次 Tailscale（免費），之後不用開通道、也不用輸入密碼，只有登入同一個 Tailscale 帳號的裝置連得到。

在伺服器上：

```
bash ~/TradingAgents/deploy/setup_tailscale.sh
```

第一次會印出一個登入網址，用瀏覽器打開並登入（Google、Microsoft 或 GitHub 帳號都可以）。如果接著又印出一個「enable HTTPS」的網址，也打開按同意，然後再執行一次這個腳本。完成時會顯示網址，格式像 `https://linux-server-505.xxxx.ts.net`。

在 Mac 和手機上安裝 Tailscale App，用同一個帳號登入，然後打開那個網址即可。

### B. HTTPS＋帳號密碼（在不能裝 App 的電腦上用）

由 Caddy 提供 HTTPS（自動申請、自動更新 Let's Encrypt 憑證）和登入視窗，網址預設為 `https://140-113-59-122.sslip.io`（不需要自己設定 DNS）。

在伺服器上：

```
bash ~/TradingAgents/deploy/setup_https.sh
```

腳本會請您設定密碼（至少 12 個字元；直接按 Enter 會產生一組強密碼並顯示一次，請立刻存到密碼管理器）。之後要換密碼，再執行一次即可；要關閉：`sudo systemctl disable --now caddy`。

需要注意：

- 伺服器的 80、443 port 必須能從外網連到（80 用來申請憑證）。如果腳本最後顯示連不到，多半是學校或機房的防火牆擋住，請網管開放，或改用 A。
- 這種方式等於把登入頁放在公網上，請用夠長、只在這裡用的密碼。登入紀錄在 `/var/log/caddy/tradingagents-access.log`。

### C. SSH 通道

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
| 手動檢查一次警示 | `sudo systemctl start tradingagents-alerts` |
| 更新程式碼（在 Mac 上 push 之後；會沿用原本的 port） | `bash ~/TradingAgents/deploy/install.sh` |

每日選股的進度和紀錄也會出現在網頁「產生報告」頁的工作列表裡，結果在「報告與建議」頁。

## 四、選填設定（台股籌碼、通知）

在伺服器的 `~/TradingAgents/.env` 加上以下幾行（已經存在的 .env 不會自動加，要自己補），改完執行 `sudo systemctl restart tradingagents-web`：

```
FINMIND_TOKEN=您的 token
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

- **FINMIND_TOKEN**：到 finmindtrade.com 免費註冊後，在會員頁取得。有了它，個股頁會多出三大法人、融資融券、月營收與除權息；AI 分析台股時也會拿到這些資料。
- **Telegram**：取得 bot token 和 chat id 的步驟寫在網頁「設定與費用 → 通知管道」頁，也可以改用 Email。設定好後，每日選股結果和警示會推送到手機。

警示在週一到週五 14:10（台股收盤後）與每日更新時各檢查一次，規則在「設定與費用 → 警示規則」頁調整。

## 五、費用與注意事項

- **費用**：每天 20 次完整分析，每次大約 11 次 LLM 呼叫，另外加上新聞摘要。網頁「設定與費用」頁會記錄每次呼叫的 token 數並換算成美元，也可以設定每日／每月上限（預設每日 30、每月 400 美元），超過上限時會自動暫停排程並通知您。第一週建議對照 OpenAI 後台的實際帳單，確認估算準確後再調整上限。
- **資料**：伺服器上的報告、自選股、新聞摘要快取放在 `~/TradingAgents/webapp_data`、`~/TradingAgents/recommendations` 和 `~/.tradingagents`。它們跟您 Mac 上的是兩份各自獨立的資料，不會同步。
- **key 的權限**：`.env` 的權限設成只有您的帳號能讀（600）。
- **不要把網頁直接開放到外網**：這個介面可以觸發會花錢的分析，也存有持倉，所以網頁只聽 127.0.0.1，外面一律經由 Tailscale、Caddy（HTTPS＋密碼）或 SSH 通道進來。不要把 `--server.address` 改成 0.0.0.0。
- **性質**：輸出是研究參考，不是投資建議。
