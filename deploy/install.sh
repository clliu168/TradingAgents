#!/usr/bin/env bash
# Install / update the TradingAgents dashboard on an Ubuntu/Debian server.
#
#   bash install.sh                 # first install, or re-run to update
#
# Settings (environment variables, all optional):
#   APP_DIR   where the repo lives            (default: ~/TradingAgents)
#   REPO_URL  git repository                  (default: your fork)
#   BRANCH    branch to deploy                (default: taiwan-horizon)
#   PORT      web port on 127.0.0.1           (default: 8501)
#   TOP       daily picks per market/horizon  (default: 5)
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/TradingAgents}"
REPO_URL="${REPO_URL:-https://github.com/clliu168/TradingAgents.git}"
BRANCH="${BRANCH:-taiwan-horizon}"
PORT="${PORT:-8501}"
TOP="${TOP:-5}"
RUN_USER="$(id -un)"

say() { printf '\n==> %s\n' "$*"; }

if [ "$(id -u)" -eq 0 ]; then
  echo "Run this as your normal user (it uses sudo only where needed), not as root." >&2
  exit 1
fi
command -v systemctl >/dev/null || { echo "systemd is required." >&2; exit 1; }

say "System packages (git, curl)"
if ! command -v git >/dev/null || ! command -v curl >/dev/null; then
  sudo apt-get update -y && sudo apt-get install -y git curl
fi

say "uv (Python manager)"
if ! command -v uv >/dev/null && [ ! -x "$HOME/.local/bin/uv" ]; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="$HOME/.local/bin:$PATH"

say "Code: $REPO_URL ($BRANCH) -> $APP_DIR"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch origin "$BRANCH"
  git -C "$APP_DIR" checkout "$BRANCH"
  git -C "$APP_DIR" merge --ff-only "origin/$BRANCH"
else
  git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

say "Python environment"
[ -d .venv ] || uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[web]"

say "Secrets (.env)"
if [ ! -f .env ]; then
  cp .env.example .env
  cat >> .env <<'ENV'

# --- server settings ---
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_OUTPUT_LANGUAGE=Traditional Chinese
SEC_EDGAR_USER_AGENT=Your Name your@email.com
# Taiwan chips / monthly revenue / dividends (free account at finmindtrade.com)
FINMIND_TOKEN=
# Notifications (fill one or both; see the 設定與費用 page)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
#SMTP_HOST=smtp.gmail.com
#SMTP_PORT=587
#SMTP_USER=
#SMTP_PASSWORD=
#NOTIFY_EMAIL_TO=
ENV
  echo "Created .env — put your OPENAI_API_KEY in it before the first daily run."
fi
chmod 600 .env

say "systemd units"
for unit in tradingagents-web.service tradingagents-daily.service tradingagents-daily.timer \
            tradingagents-alerts.service tradingagents-alerts.timer; do
  sed -e "s|@USER@|$RUN_USER|g" -e "s|@APP_DIR@|$APP_DIR|g" \
      -e "s|@PORT@|$PORT|g" -e "s|@TOP@|$TOP|g" \
      "deploy/systemd/$unit" | sudo tee "/etc/systemd/system/$unit" >/dev/null
done
sudo systemctl daemon-reload
sudo systemctl enable --now tradingagents-web.service tradingagents-daily.timer tradingagents-alerts.timer
sudo systemctl restart tradingagents-web.service

say "Check"
sleep 5
if curl -fsS -o /dev/null "http://127.0.0.1:$PORT/_stcore/health"; then
  echo "Web dashboard is up on 127.0.0.1:$PORT"
else
  echo "Web dashboard did not answer yet; see: journalctl -u tradingagents-web -n 50" >&2
fi
systemctl list-timers 'tradingagents-*' --no-pager || true
for key in FINMIND_TOKEN TELEGRAM_BOT_TOKEN; do
  grep -Eq "^$key=.+" .env || echo "Optional: $key is not set in .env (see deploy/README_DEPLOY_zh-TW.md)."
done
if ! grep -Eq '^OPENAI_API_KEY=.+' .env; then
  echo
  echo "NOTE: OPENAI_API_KEY is empty in $APP_DIR/.env — edit it (nano $APP_DIR/.env), then:"
  echo "      sudo systemctl restart tradingagents-web"
fi
