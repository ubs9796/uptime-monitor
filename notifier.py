import json
import os
import urllib.error
import urllib.request

from checker import validate_https_url


def format_alert_message(
    client_name: str,
    url: str,
    is_up: bool,
    status_code: int,
    ssl_days: int | None,
    ssl_warn_days: int = 14,
) -> str:
    """Build a concise alert string for downtime, recovery, or SSL expiry."""
    state = "RECOVERED" if is_up else "DOWN"
    lines = [
        f"[{state}] {client_name}",
        f"URL: {url}",
        f"HTTP Status: {status_code}",
    ]
    if ssl_days is not None and ssl_days <= ssl_warn_days:
        lines.append(f"SSL Warning: {ssl_days} days left")
    return "\n".join(lines)


def send_telegram_alert(
    message: str,
    bot_token: str | None = None,
    chat_id: str | None = None,
    timeout_sec: float = 5.0,
) -> bool:
    """Send alert message via Telegram Bot API using env credentials."""
    token = (bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
    target_chat = (chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
    if not token or not target_chat:
        return False

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": target_chat, "text": message}).encode("utf-8")
    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "bsloopstudio-uptime/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return 200 <= resp.getcode() < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def send_webhook_alert(message: str, webhook_url: str | None = None, timeout_sec: float = 5.0) -> bool:
    """Send alert via Telegram if configured, otherwise fall back to ALERT_WEBHOOK_URL."""
    if send_telegram_alert(message, timeout_sec=timeout_sec):
        return True

    target = webhook_url or os.environ.get("ALERT_WEBHOOK_URL", "")
    if not target.strip():
        return False
    try:
        clean_url = validate_https_url(target)
    except ValueError:
        return False
    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        clean_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "bsloopstudio-uptime/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return 200 <= resp.getcode() < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
