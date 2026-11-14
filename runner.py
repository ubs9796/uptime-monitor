import argparse
import json
import os
import socket
import ssl
import sys
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

from checker import check_http_status, get_ssl_days_left, is_internet_online
from notifier import format_alert_message, send_webhook_alert
from storage import (
    add_site,
    connect_db,
    init_db,
    list_sites,
    prune_check_history,
    remove_site,
    update_site_state,
)

DEFAULT_CHECK_WORKERS = 4
MAX_CHECK_WORKERS = 32


def extract_hostname(url: str) -> str:
    """Return hostname from a validated HTTP/HTTPS URL."""
    parsed = urllib.parse.urlparse(url)
    if not parsed.hostname:
        raise ValueError(f"Missing hostname in URL: {url}")
    return parsed.hostname


def resolve_check_workers(workers: int | None = None) -> int:
    """Resolve bounded check concurrency from the argument or environment."""
    if workers is None:
        raw = os.environ.get("UPTIME_CHECK_WORKERS", str(DEFAULT_CHECK_WORKERS))
        try:
            workers = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"UPTIME_CHECK_WORKERS must be an integer, got {raw!r}.") from exc
    if isinstance(workers, bool) or not isinstance(workers, int):
        raise ValueError("workers must be an integer.")
    if not (1 <= workers <= MAX_CHECK_WORKERS):
        raise ValueError(f"workers must be between 1 and {MAX_CHECK_WORKERS}.")
    return workers


def check_site(url: str) -> tuple[bool, int, int | None]:
    """Run HTTP and TLS checks for one site without touching the database."""
    is_up, status_code = check_http_status(url)
    ssl_days: int | None = None
    if url.startswith("https://"):
        try:
            hostname = extract_hostname(url)
            ssl_days = get_ssl_days_left(hostname)
        except (socket.timeout, ssl.SSLError, OSError, ValueError):
            ssl_days = None
    return is_up, status_code, ssl_days


def run_check_cycle(
    db_path: str = "uptime.db",
    ssl_warn_days: int = 14,
    probe_url: str = "https://1.1.1.1",
    workers: int | None = None,
) -> dict[str, int]:
    """Check all stored sites once, update changed state, and dispatch alerts."""
    worker_count = resolve_check_workers(workers)
    if not is_internet_online(probe_url=probe_url):
        return {"checked": 0, "changed": 0, "alerts_sent": 0, "skipped_offline": 1}

    conn = connect_db(db_path)
    init_db(conn)
    sites = list_sites(conn)

    checked = 0
    changed = 0
    alerts_sent = 0

    try:
        urls = [site["url"] for site in sites]
        if worker_count > 1 and len(urls) > 1:
            with ThreadPoolExecutor(max_workers=min(worker_count, len(urls))) as pool:
                results = list(pool.map(check_site, urls))
        else:
            results = [check_site(url) for url in urls]

        for site, (is_up, status_code, ssl_days) in zip(sites, results):
            checked += 1
            url = site["url"]
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

    remove_cmd = sub.add_parser("remove", help="Stop monitoring a website")
    remove_cmd.add_argument("url", help="Exact URL that was added")

    list_cmd = sub.add_parser("list", help="List all monitored websites and last status")
    list_cmd.add_argument("--json", action="store_true", help="Output sites as JSON")

    check_cmd = sub.add_parser("check", help="Run one check cycle across all sites")
    check_cmd.add_argument("--ssl-warn-days", type=int, default=14, help="Days before SSL expiry to alert")
    check_cmd.add_argument(
        "--workers",
        type=int,
        default=None,
        help=(
            f"Concurrent site checks (1-{MAX_CHECK_WORKERS}); "
            f"defaults to UPTIME_CHECK_WORKERS or {DEFAULT_CHECK_WORKERS}"
        ),
    )

    prune_cmd = sub.add_parser("prune", help="Delete check history older than a retention period")
    prune_cmd.add_argument(
        "--days",
        type=int,
        required=True,
        help="Retention period in days (must be at least 1)",
    )
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

    if args.command == "remove":
        conn = connect_db(args.db)
        init_db(conn)
        try:
            if not remove_site(conn, args.url):
                print(f"Site not found: {args.url}", file=sys.stderr)
                return 1
            print(f"Removed site: {args.url}")
        finally:
            conn.close()
        return 0

    if args.command == "list":
        conn = connect_db(args.db)
        init_db(conn)
        try:
            sites = list_sites(conn)
            if args.json:
                print(json.dumps(sites, indent=2))
                return 0
            if not sites:
                print("No sites configured.")
                return 0
            for s in sites:
                state = "NEW" if s["last_is_up"] is None else ("UP" if s["last_is_up"] == 1 else "DOWN")
                status_code = "-" if s["last_status_code"] is None else s["last_status_code"]
                ssl_days = "-" if s["last_ssl_days"] is None else f"{s['last_ssl_days']}d"
                print(f"[{s['id']}] {s['client_name']} | {s['url']} | {state} ({status_code}) | SSL: {ssl_days}")
        finally:
            conn.close()
        return 0

    if args.command == "check":
        try:
            summary = run_check_cycle(
                db_path=args.db,
                ssl_warn_days=args.ssl_warn_days,
                workers=args.workers,
            )
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        print(f"Cycle complete: {summary}")
        return 0

    if args.command == "prune":
        conn = connect_db(args.db)
        init_db(conn)
        try:
            deleted = prune_check_history(conn, args.days)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
        finally:
            conn.close()
        print(f"Pruned {deleted} check-history row(s) older than {args.days} day(s).")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
