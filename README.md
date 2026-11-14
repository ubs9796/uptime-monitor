This repo is a lightweight uptime and SSL monitor for websites, built in pure Python with no third-party libraries.

What it does:
- Checks whether a website is reachable over HTTP/HTTPS
- Tracks HTTP status codes
- Watches TLS/SSL certificate expiry for HTTPS sites
- Stores results in SQLite
- Sends alerts when status changes
- Shows a simple dashboard in the browser

In other words, it is a small monitoring tool for people who want to know:
- "Is my site down?"
- "Did my certificate expire?"
- "Did the HTTP response change unexpectedly?"

What is in the project:
- runner.py: command-line tool to add/remove/list/check/prune sites and run the check cycle
- checker.py: performs connectivity and HTTP/SSL checks
- storage.py: stores site state and historical check results in SQLite
- notifier.py: formats alert messages and sends them to Telegram or a webhook
- dashboard.py: shows a basic HTML dashboard with site status
- sites.example.json: example site configuration
- .env.example: environment variable names for secrets

How it works:
- You add a site with a name and URL
- The monitor runs a check cycle
- It probes the internet first using 1.1.1.1
- If the network is reachable, it checks all configured URLs
- For HTTP sites, it verifies the request succeeds and records the response status
- For HTTPS sites, it also checks how many days remain before the cert expires
- If a site changes state or the SSL warning threshold is crossed, it triggers an alert
- Results are stored in a local SQLite database

Alert behavior:
- Alerts are triggered when the site flips from up to down, or down to up
- It also alerts on HTTP code changes
- It alerts when SSL warning thresholds are reached
- It does not spam repeated identical checks

Important design choices:
- Zero dependency: no heavy monitoring stack, no Redis, no Docker requirement
- Local-first: it stores data on the machine running it
- Small-footprint: designed to run on a Raspberry Pi or similar low-power host
- Security-conscious: it avoids writing secrets to source files; environment variables are used instead

Setup:
- Requires Python 3.10+
- Copy sites.example.json to sites.json and add your sites
- Set Telegram or webhook environment variables only if you want alerts

Typical usage:
- Add a client and URL:
  - python3 runner.py add "Example Clinic" "https://example.com"
- Run one check:
  - python3 runner.py check
- View configured sites:
  - python3 runner.py list
- Start the dashboard:
  - python3 dashboard.py
- Delete check history older than 90 days:
  - python3 runner.py prune --days 90

Dashboard:
- The dashboard is a simple HTML page showing:
  - client/site name
  - URL
  - status (UP/DOWN)
  - HTTP code
  - SSL expiry days
  - last updated time
- It is read-only and has basic auth protections if exposed beyond localhost
- It uses a threaded HTTP server so one slow request does not block others
- Each request still opens its own SQLite connection; authentication and response headers are unchanged

Environment variables:
- TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID: optional Telegram notifications
- ALERT_WEBHOOK_URL: optional fallback webhook receiver
- UPTIME_DASHBOARD_TOKEN: required if the dashboard is bound externally
- UPTIME_HOST, UPTIME_PORT, UPTIME_DB_PATH: optional server configuration
- UPTIME_CHECK_WORKERS: optional concurrent check workers, 1-32 (default 4)

Check concurrency:
- HTTP and TLS checks run through a bounded thread pool
- Set the worker count with --workers or UPTIME_CHECK_WORKERS
- Database writes and alerts stay sequential in site order, so state and alert behavior are unchanged
- More workers shorten batches but increase simultaneous connections and memory use

History retention:
- Every check is appended to the checks history table; the current-state row is written only on transitions
- History is never pruned automatically
- Run python3 runner.py prune --days N to delete rows strictly older than N days; rows exactly at the cutoff are kept
- Pruning is permanent, and the database file may not shrink until SQLite reuses the freed pages
- Deleting a site cascades its history, and SQLite secure_delete overwrites freed rows

Limitations:
- Single-process SQLite, not for very high concurrency
- No user accounts or rate limiting on the dashboard; threading improves responsiveness, not abuse resistance
- No email or SMS support
- Dashboard is plain HTTP unless behind a TLS reverse proxy
- It relies on a connectivity probe to 1.1.1.1; if that network is blocked, checks may be skipped
- Bounded check concurrency shortens cycles, but the slowest site in each batch still bounds that batch; raise workers cautiously on a Pi 3B
- Check history grows until an operator runs prune; schedule it deliberately if retention matters, since there is no automatic retention policy
- GitHub Actions state is cache-based and best-effort; a cache miss resets history
- No encryption at rest; use full-disk encryption on the host
- Not a HIPAA, PCI DSS, or SOC 2 certification; see COMPLIANCE.md

Testing:

    pytest -v

The suite covers URL validation, HTTP errors and timeouts, SSL expiry boundaries, storage transitions and history, pruning cutoffs and invalid retention values, worker-count boundaries and concurrent/network-failure check cycles, notifier environment isolation, and dashboard XSS, auth, headers, port validation, and concurrent requests.

Best way to think about this project:
- It is not a full SaaS monitoring platform
- It is more like a tiny self-hosted health monitor for a handful of websites and SSL certs
- It is ideal if you want a simple, local, low-cost monitoring setup without paying for a hosted service

License: MIT License - Copyright (c) 2026 Bharath Simha (bsloopstudio)
