This repo is a lightweight uptime and SSL monitor for websites, built in pure Python with no third-party libraries.

What it does:
- Checks whether a website is reachable over HTTP/HTTPS
- Tracks HTTP status codes
- Watches TLS/SSL certificate expiry for HTTPS sites
- Stores results in SQLite
- Sends alerts when status changes
- Shows a simple dashboard in the browser

In other words, it’s a small monitoring tool for people who want to know:
- “Is my site down?”
- “Did my certificate expire?”
- “Did the HTTP response change unexpectedly?”

What’s in the project:
- runner.py: command-line tool to add/remove/list/check sites
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
- If a site changes state or SSL warning threshold is crossed, it triggers an alert
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

Dashboard:
- The dashboard is a simple HTML page showing:
  - client/site name
  - URL
  - status (UP/DOWN)
  - HTTP code
  - SSL expiry days
  - last updated time
- It is read-only and has basic auth protections if exposed beyond localhost

Typical usage:
- Add a client and URL:
  - python3 runner.py add "Example Clinic" "https://example.com"
- Run one check:
  - python3 runner.py check
- View configured sites:
  - python3 runner.py list
- Start the dashboard:
  - python3 dashboard.py

Environment variables:
- TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID: optional Telegram notifications
- ALERT_WEBHOOK_URL: optional fallback webhook receiver
- UPTIME_DASHBOARD_TOKEN: required if the dashboard is bound externally
- UPTIME_HOST, UPTIME_PORT, UPTIME_DB_PATH: optional server configuration

Limitations:
- Single-process SQLite, not for very high concurrency
- No user accounts or rate limiting on the dashboard
- No email or SMS support
- Dashboard is plain HTTP unless behind a TLS reverse proxy
- It relies on a connectivity probe to 1.1.1.1; if that network is blocked, checks may be skipped

Best way to think about this project:
- It’s not a full SaaS monitoring platform
- It’s more like a tiny self-hosted health monitor for a handful of websites and SSL certs
- It’s ideal if you want a simple, local, low-cost monitoring setup without paying for a hosted service

If you want, I can also:
- walk through the code flow step by step,
- explain the database schema,
- show how to configure it for your own sites,
- or summarize the project in “beginner-friendly” terms.
