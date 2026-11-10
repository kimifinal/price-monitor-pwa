"""
Telegram alert stub.

Sends a message to a Telegram chat via the Bot API. Fill in TELEGRAM_BOT_TOKEN
and TELEGRAM_CHAT_ID in .env (copy .env.example) to make it real.
"""
import os
import json
import urllib.request
import urllib.error
import urllib.parse

BOT_API = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram_alert(item, price) -> bool:
    """Send a Telegram alert when `price <= item.target`.

    Returns True if the send was attempted successfully, False if no token/chat
    is configured (so the pipeline can run without credentials).
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        # No credentials configured — log instead of sending.
        print(f"[alert] {item.name}: {price} <= {item.target}")
        return False

    text = (
        f"🔔 跌破目標價\n"
        f"{item.name}: ${price:.2f}（目標 ${item.target:.2f}）"
    )
    url = BOT_API.format(token=token) + f"?chat_id={chat_id}&text=" + urllib.parse.quote(
        text
    )
    try:
        req = urllib.request.Request(url, method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status == 200
    except (urllib.error.URLError, OSError):
        return False
