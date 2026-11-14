# Website Uptime & SSL Expiry Monitor

A lightweight, zero-dependency Python 3 tool that monitors HTTP availability and TLS/SSL certificate expiry across configured websites, stores state in SQLite (WAL mode), and sends instant alerts via Telegram Bot or webhooks.

## Features
- Zero external runtime dependencies: Built purely with Python 3 standard libraries (<60 MB RAM).
- State-transition alerts: Alerts only on UP/DOWN changes or SSL expiry warnings.
- Check history: Every check is recorded in a `checks` table (cascade-deleted with its site).
- 24/7 Cloud Cron: Includes .github/workflows/monitor.yml for automated 10-minute checks.
- Read-only Web Dashboard: HTML-escaped status server (dashboard.py).

## Quick Start
    python3 runner.py add "Google India" "https://www.google.com"
    python3 runner.py check --ssl-warn-days 14
    python3 runner.py list
    python3 runner.py list --json
    python3 runner.py remove "https://www.google.com"

## Testing
    pytest -v

## License
MIT License - Copyright (c) 2026 Bharath Simha (bsloopstudio)
