# Website Uptime & SSL Expiry Monitor

A zero-dependency Python 3 monitor for HTTP uptime and TLS certificate expiry. State is stored in SQLite (WAL mode); alerts go to Telegram or a JSON webhook. Runs in under 60 MB RAM on a Raspberry Pi 3B.

## Quick Start
    cp sites.example.json sites.json   # then edit your sites
    # export TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in your shell
    python3 runner.py add "Example" "https://example.com"
    python3 runner.py check
    python3 runner.py list

## Environment
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`: Telegram alerts.
- `ALERT_WEBHOOK_URL`: HTTPS fallback webhook that receives `{"text": "..."}`.
- `UPTIME_DASHBOARD_TOKEN`: required if `UPTIME_HOST` is not loopback; send as `Authorization: Bearer`.

Secrets are read from the environment only; never commit them. See `.env.example` and `COMPLIANCE.md`.

## Commands
    python3 runner.py add "Name" "https://url"
    python3 runner.py remove "https://url"
    python3 runner.py check [--ssl-warn-days 14]
    python3 runner.py list [--json]
    python3 dashboard.py    # UPTIME_HOST, UPTIME_PORT, UPTIME_DB_PATH

## Testing
    pytest -v

## License
MIT License - Copyright (c) 2026 Bharath Simha (bsloopstudio)
