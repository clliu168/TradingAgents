#!/usr/bin/env bash
# Private access over Tailscale: open the dashboard from your own devices at
#   https://<this-machine>.<your-tailnet>.ts.net
# with no SSH tunnel and no port opened to the internet.
#
#   bash deploy/setup_tailscale.sh
#
# Then install the Tailscale app on your Mac / phone and sign in with the same account.
set -euo pipefail

WEB_UNIT=/etc/systemd/system/tradingagents-web.service
PORT="${PORT:-$(grep -oE -- '--server\.port [0-9]+' "$WEB_UNIT" 2>/dev/null | awk '{print $2}' || true)}"
PORT="${PORT:-8501}"

say() { printf '\n==> %s\n' "$*"; }

if ! curl -fsS -o /dev/null "http://127.0.0.1:$PORT/_stcore/health"; then
  echo "The dashboard is not answering on 127.0.0.1:$PORT. Run deploy/install.sh first." >&2
  exit 1
fi

say "Tailscale"
if ! command -v tailscale >/dev/null; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

if ! tailscale status >/dev/null 2>&1; then
  say "Sign in: open the URL below in a browser and log in (Google / Microsoft / GitHub account)"
  sudo tailscale up
fi

say "Publishing 127.0.0.1:$PORT inside your tailnet (HTTPS, tailnet members only)"
# The first time, this prints a link to enable HTTPS certificates for your tailnet; open it, then re-run.
sudo tailscale serve --bg --https=443 "http://127.0.0.1:$PORT"
tailscale serve status

name="$(tailscale status --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || true)"
echo
echo "Done. On any device signed in to the same Tailscale account, open:"
echo "    https://${name:-<machine>.<tailnet>.ts.net}"
echo "To stop sharing:  sudo tailscale serve --https=443 off"
