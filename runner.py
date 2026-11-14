import argparse
import os
import socket
import ssl
import urllib.parse

from checker import check_http_status, get_ssl_days_left, is_internet_online
from notifier import format_alert_message, send_webhook_alert
from storage import add_site, connect_db, init_db, list_sites, update_site_state


def extract_hostname(url: str) -> str:
    """Return hostname from a validated HTTP/HTTPS URL."""
    parsed = urllib.parse.urlparse(url)
    if not parsed.hostname:
        raise ValueError(f"Missing hostname in URL: {url}")
    return parsed.hostname


def run_check_cycle(
    db_path: str = "uptime.db",
    ssl_warn_days: int = 14,
    probe_url: str = "https://1.1.1.1",
) -> dict[str, int]:
    """Check all stored sites once, update changed state, and dispatch alerts."""
    if not is_internet_online(probe_url=probe_url):
        return {"checked": 0, "changed": 0, "alerts_sent": 0, "skipped_offline": 1}

    conn = connect_db(db_path)
    init_db(conn)
    sites = list_sites(conn)

    checked = 0
    changed = 0
    alerts_sent = 0

    try:
        for site in sites:
            checked += 1
            url = site["url"]
            is_up, status_code = check_http_status(url)

            ssl_days: int | None = None
            if url.startswith("https://"):
                try:
                    hostname = extract_hostname(url)
                    ssl_days = get_ssl_days_left(hostname)
                except (socket.timeout, ssl.SSLError, OSError, ValueError):
                    ssl_days = None

            ssl_alert_needed = ssl_days is not None and ssl_days <= ssl_warn_days
            state_changed = update_site_state(
                conn=conn,
                site_id=site["id"],
                is_up=is_up,
                status_code=status_code,
                ssl_days=ssl_days,
                ssl_alert_sent=ssl_alert_needed,
            )

            if state_changed:
                changed += 1
                msg = format_alert_message(
                    client_name=site["client_name"],
                    url=url,
                    is_up=is_up,
                    status_code=status_code,
                    ssl_days=ssl_days,
                    ssl_warn_days=ssl_warn_days,
                )
                if send_webhook_alert(msg):
                    alerts_sent += 1
    finally:
        conn.close()

    return {"checked": checked, "changed": changed, "alerts_sent": alerts_sent, "skipped_offline": 0}


def build_parser() -> argparse.ArgumentParser:
    """Create CLI parser for adding sites, listing sites, and running checks."""
    parser = argparse.ArgumentParser(description="bsloopstudio Uptime & SSL Monitor")
    parser.add_argument(
        "--db",
        default=os.environ.get("UPTIME_DB_PATH", "uptime.db"),
        help="Path to SQLite database file",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    add_cmd = sub.add_parser("add", help="Add a customer website to monitor")
    add_cmd.add_argument("client_name", help="Customer or clinic name")
    add_cmd.add_argument("url", help="Full http:// or https:// URL")

    sub.add_parser("list", help="List all monitored websites and last status")

    check_cmd = sub.add_parser("check", help="Run one check cycle across all sites")
    check_cmd.add_argument("--ssl-warn-days", type=int, default=14, help="Days before SSL expiry to alert")
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args = build_parser().parse_args(argv)
    if args.command == "add":
        conn = connect_db(args.db)
        init_db(conn)
        try:
            site_id = add_site(conn, args.client_name, args.url)
            print(f"Added site #{site_id}: {args.client_name} -> {args.url}")
        finally:
            conn.close()
        return 0

    if args.command == "list":
        conn = connect_db(args.db)
        init_db(conn)
        try:
            sites = list_sites(conn)
            if not sites:
                print("No sites configured.")
                return 0
            for s in sites:
                state = "NEW" if s["last_is_up"] is None else ("UP" if s["last_is_up"] == 1 else "DOWN")
                print(f"[{s['id']}] {s['client_name']} | {s['url']} | {state} ({s['last_status_code']}) | SSL: {s['last_ssl_days']}d")
        finally:
            conn.close()
        return 0

    if args.command == "check":
        summary = run_check_cycle(db_path=args.db, ssl_warn_days=args.ssl_warn_days)
        print(f"Cycle complete: {summary}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
