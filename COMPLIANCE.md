# Compliance scope

This is an uptime monitor, not a PHI or cardholder-data system. It stores only site labels, public URLs, HTTP status, SSL days, and timestamps in SQLite. It does not collect visitor data, cookies, PHI, or cardholder data, so HIPAA, PCI DSS, and GDPR consent flows do not apply to the code itself.

Operators are responsible for:
- Data at rest: use full-disk encryption on the host and restrict the database file to the service user.
- Access: keep the dashboard on loopback or set `UPTIME_DASHBOARD_TOKEN`; non-loopback dashboard traffic is plain HTTP, so put it behind a TLS reverse proxy. Webhook alerts require HTTPS.
- Erasure: `python3 runner.py remove URL` cascades history, and `secure_delete` overwrites freed rows.
- Retention: remove sites you no longer need; the `checks` table and CI logs are the audit trail.
- Breach response: follow your legal notification timelines and report code issues via `SECURITY.md`.

This document is not a compliance certification.
