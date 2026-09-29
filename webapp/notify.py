"""Send a message to Telegram and/or e-mail, whichever is configured in .env.

Telegram:  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
E-mail:    SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, NOTIFY_EMAIL_TO
           (Gmail: smtp.gmail.com with an app password)

Nothing configured -> send() is a no-op that returns an empty list.
"""

from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from webapp.jobs import ROOT


def _env() -> dict:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    return os.environ


def channels() -> list[str]:
    env = _env()
    out = []
    if env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"):
        out.append("telegram")
    if env.get("SMTP_HOST") and env.get("SMTP_USER") and env.get("SMTP_PASSWORD") and env.get("NOTIFY_EMAIL_TO"):
        out.append("email")
    return out


def _telegram(text: str, env) -> None:
    import requests

    # Telegram caps a message at 4096 characters.
    for i in range(0, len(text), 4000):
        r = requests.post(f"https://api.telegram.org/bot{env['TELEGRAM_BOT_TOKEN']}/sendMessage",
                          json={"chat_id": env["TELEGRAM_CHAT_ID"], "text": text[i:i + 4000],
                                "disable_web_page_preview": True}, timeout=20)
        r.raise_for_status()


def _email(text: str, subject: str, env) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = env["SMTP_USER"]
    msg["To"] = env["NOTIFY_EMAIL_TO"]
    msg.set_content(text)
    with smtplib.SMTP(env["SMTP_HOST"], int(env.get("SMTP_PORT") or 587), timeout=30) as s:
        s.starttls()
        s.login(env["SMTP_USER"], env["SMTP_PASSWORD"])
        s.send_message(msg)


def send(text: str, subject: str = "TradingAgents 通知") -> list[str]:
    """Deliver ``text`` on every configured channel; return the ones that succeeded."""
    env = _env()
    sent = []
    for ch in channels():
        try:
            if ch == "telegram":
                _telegram(text, env)
            else:
                _email(text, subject, env)
            sent.append(ch)
        except Exception as exc:  # noqa: BLE001 — one channel failing must not stop the other
            print(f"notify via {ch} failed: {exc}", flush=True)
    return sent
