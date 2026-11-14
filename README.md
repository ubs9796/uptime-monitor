# Uptime Monitor

## What it is

A small, standard-library-only Python 3 tool that checks HTTP availability and TLS certificate expiry for a list of websites. Results are stored in SQLite, alerts go to Telegram or an HTTPS webhook, and a read-only web dashboard shows the current state.

## Why it exists

Small hosting clients need to know when a site goes down or a certificate is about to expire without paying for a heavyweight monitoring service. This runs on a Raspberry Pi 3B (under 60 MB RAM) or a Chromebook and has no runtime dependencies.

## Files

| File | Purpose |
|---|---|
| `runner.py` | CLI (`add`, `remove`, `check`, `list`) and the check cycle |
| `checker.py` | URL validation, HTTP status, TLS expiry, connectivity probe |
| `storage.py` | SQLite schema, current state, and check history |
| `notifier.py` | Alert formatting and Telegram/webhook delivery |
| `dashboard.py` | Read-only HTML status server |
| `test_*.py` | Test suite |
| `sites.example.json` | Example site list; copy to the ignored `sites.json` |
| `.env.example` | Environment variable names only |
| `.github/workflows/monitor.yml` | 10-minute GitHub Actions cron |
| `SECURITY.md` | Vulnerability reporting |
| `COMPLIANCE.md` | Data scope and operator responsibilities |
| `CONTRIBUTING.md` | Contribution and commit rules |

## Setup

Requires Python 3.10+.

    cp sites.example.json sites.json      # add your sites locally
    export TELEGRAM_BOT_TOKEN=...         # optional Telegram alerting
    export TELEGRAM_CHAT_ID=...
    python3 runner.py add "Example" "https://example.com"
    python3 runner.py check
    python3 runner.py list

Dashboard:

    python3 dashboard.py                  # http://127.0.0.1:8080

Set `UPTIME_HOST=0.0.0.0` only with `UPTIME_DASHBOARD_TOKEN` set and a TLS reverse proxy in front.

| Variable | Required | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Optional pair | Telegram alerts |
| `ALERT_WEBHOOK_URL` | Optional | HTTPS fallback receiving `{"text": "..."}` |
| `UPTIME_DASHBOARD_TOKEN` | Non-loopback bind | Bearer token for the dashboard |
| `UPTIME_HOST`, `UPTIME_PORT`, `UPTIME_DB_PATH` | Optional | Dashboard bind and database path |

Secrets come from the environment only; never commit them.

## Behaviour

- A pre-flight probe to `https://1.1.1.1` skips the whole cycle when the monitor is offline.
- HTTP status below 500 counts as up; 5xx and network errors count as down. A 4xx response is therefore treated as up.
- TLS expiry is checked only for `https://` URLs, on port 443.
- Alerts fire when a site flips up/down, its HTTP code changes, or the SSL-warning state changes. Repeated identical checks do not alert.
- Every check is appended to the `checks` history table; the current-state row is written only on transitions.
- Deleting a site cascades its history, and SQLite `secure_delete` overwrites freed rows.
- Telegram is tried first; the HTTPS webhook is the fallback.
- The dashboard escapes dynamic values and sends CSP, frame, referrer, and no-store headers.

## Limitations

- The dashboard speaks plain HTTP. A non-loopback bind needs a TLS reverse proxy, or the bearer token travels in clear text.
- No rate limiting, user accounts, or brute-force protection on the dashboard.
- Telegram and webhooks only; no email or SMS.
- Single-process SQLite; not designed for high write concurrency.
- GitHub Actions state is cache-based and best-effort; a cache miss resets history.
- The connectivity probe depends on `1.1.1.1`; networks that block it skip every cycle.
- No encryption at rest; use full-disk encryption on the host.
- Not a HIPAA, PCI DSS, or SOC 2 certification. See `COMPLIANCE.md`.

## Testing

    pytest -v

The suite covers URL validation, HTTP errors and timeouts, SSL expiry boundaries, storage transitions and history, notifier environment isolation, and dashboard XSS, auth, and headers.

## License

MIT License - Copyright (c) 2026 Bharath Simha (bsloopstudio)
