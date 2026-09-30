#!/usr/bin/env bash
# Public HTTPS access with a login prompt, for browsers where you can't install Tailscale.
# Caddy terminates HTTPS (free Let's Encrypt certificate, auto-renewed), asks for a
# username/password, and forwards to the dashboard, which itself stays on 127.0.0.1.
#
#   bash deploy/setup_https.sh
#
# Settings (environment variables, all optional):
#   DOMAIN     host name to serve   (default: <public-ip-with-dashes>.sslip.io, needs no DNS setup)
#   WEB_USER   login name           (default: your Linux user name)
#   PORT       dashboard port       (default: the installed one)
#
# Needs ports 80 and 443 reachable from the internet (80 is used to issue the certificate).
set -euo pipefail

say() { printf '\n==> %s\n' "$*"; }
WEB_UNIT=/etc/systemd/system/tradingagents-web.service
PORT="${PORT:-$(grep -oE -- '--server\.port [0-9]+' "$WEB_UNIT" 2>/dev/null | awk '{print $2}' || true)}"
PORT="${PORT:-8501}"
WEB_USER="${WEB_USER:-$(id -un)}"
SITE_FILE=/etc/caddy/tradingagents.caddy

if ! systemctl is-active --quiet tradingagents-web \
   || ! curl -fsS -o /dev/null "http://127.0.0.1:$PORT/_stcore/health"; then
  echo "The TradingAgents web service is not running on 127.0.0.1:$PORT." >&2
  echo "Check: systemctl status tradingagents-web   (fix, then re-run this script)" >&2
  exit 1
fi

if [ -z "${DOMAIN:-}" ]; then
  ip="$(curl -fsS https://api.ipify.org || true)"
  [ -n "$ip" ] || { echo "Could not detect the public IP; set DOMAIN=..." >&2; exit 1; }
  DOMAIN="${ip//./-}.sslip.io"
fi

say "Ports 80/443"
busy="$(sudo ss -ltnpH '( sport = :80 or sport = :443 )' | grep -v caddy || true)"
if [ -n "$busy" ]; then
  echo "Port 80 or 443 is already used by another program:" >&2
  echo "$busy" >&2
  echo "Stop it (or put this site behind it) and re-run." >&2
  exit 1
fi

say "Caddy"
if ! command -v caddy >/dev/null; then
  sudo apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | sudo gpg --batch --yes --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -y && sudo apt-get install -y caddy
fi

say "Login for $WEB_USER"
if [ -z "${WEB_PASSWORD:-}" ]; then
  read -r -s -p "Choose a password (Enter = generate a strong one): " WEB_PASSWORD; echo
fi
generated=0
if [ -z "$WEB_PASSWORD" ]; then
  WEB_PASSWORD="$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)"
  generated=1
elif [ "${#WEB_PASSWORD}" -lt 12 ]; then
  echo "Use at least 12 characters: this page is on the public internet." >&2
  exit 1
fi
hash="$(caddy hash-password --plaintext "$WEB_PASSWORD")"

say "Site config: https://$DOMAIN -> 127.0.0.1:$PORT"
sudo tee "$SITE_FILE" >/dev/null <<CADDY
$DOMAIN {
	encode gzip
	basicauth {
		$WEB_USER $hash
	}
	header {
		Strict-Transport-Security "max-age=31536000"
		X-Frame-Options "DENY"
		Referrer-Policy "no-referrer"
		-Server
	}
	reverse_proxy 127.0.0.1:$PORT
	log {
		output file /var/log/caddy/tradingagents-access.log
	}
}
CADDY

# Caddy's stock Caddyfile only serves a placeholder page on :80; replace it with an import.
if ! grep -q "import tradingagents.caddy" /etc/caddy/Caddyfile 2>/dev/null; then
  # Stock file = only a ":80 { root * /usr/share/caddy; file_server }" block (plus comments).
  body="$(grep -vE '^[[:space:]]*(#|$)' /etc/caddy/Caddyfile 2>/dev/null | tr -d '[:space:]' || true)"
  if [ -z "$body" ] || [ "$body" = ":80{root*/usr/share/caddyfile_server}" ]; then
    sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.orig
    echo "import tradingagents.caddy" | sudo tee /etc/caddy/Caddyfile >/dev/null
  else
    echo "import tradingagents.caddy" | sudo tee -a /etc/caddy/Caddyfile >/dev/null
  fi
fi
sudo mkdir -p /var/log/caddy && sudo chown caddy:caddy /var/log/caddy
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
sudo systemctl enable caddy >/dev/null 2>&1
sudo systemctl restart caddy

if command -v ufw >/dev/null && sudo ufw status | grep -q "Status: active"; then
  sudo ufw allow 80/tcp >/dev/null && sudo ufw allow 443/tcp >/dev/null
fi

say "Check (the certificate can take up to a minute the first time)"
ok=0
for _ in $(seq 1 12); do
  code="$(curl -s -o /dev/null -w '%{http_code}' "https://$DOMAIN/" || true)"
  if [ "$code" = "401" ]; then ok=1; break; fi
  sleep 5
done
if [ "$ok" = 1 ]; then
  echo "HTTPS works and asks for a login."
else
  echo "Could not reach https://$DOMAIN yet. Most likely ports 80/443 are blocked by a network" >&2
  echo "firewall in front of this machine. See: journalctl -u caddy -n 50" >&2
fi
echo
echo "Open:      https://$DOMAIN"
echo "User:      $WEB_USER"
if [ "$generated" = 1 ]; then
  echo "Password:  $WEB_PASSWORD      <- save it in your password manager now; it is not stored anywhere."
fi
echo "Change the password later by re-running this script. Turn it off: sudo systemctl disable --now caddy"
