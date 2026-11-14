import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from checker import check_http_status, get_ssl_days_left, validate_url
from notifier import send_telegram_alert

LEADS_FILE = "leads.json"
SITES_FILE = "sites.json"


def load_json(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def git_sync(msg: str) -> bool:
    subprocess.run(["git", "add", LEADS_FILE, SITES_FILE], check=False)
    subprocess.run(["git", "commit", "-m", msg], check=False)
    res = subprocess.run(["git", "push", "origin", "main"], check=False)
    return res.returncode == 0


def main() -> None:
    if len(sys.argv) < 3:
        print('Usage: python3 audit.py "Business Name" "https://example.com" [--activate]')
        sys.exit(1)

    name = sys.argv[1].strip()
    url = validate_url(sys.argv[2].strip())
    activate = "--activate" in sys.argv[3:]

    host = url.split("//", 1)[1].split("/", 1)[0].split(":", 1)[0]
    try:
        http_code = check_http_status(url)
    except Exception:
        http_code = 0
    try:
        ssl_days = get_ssl_days_left(host)
    except Exception:
        ssl_days = None

    now = datetime.now(timezone.utc)
    expires = (now + timedelta(days=10)).strftime("%Y-%m-%d")

    leads = [x for x in load_json(LEADS_FILE) if x.get("url") != url]
    leads.append({
        "client_name": name,
        "url": url,
        "http_code": http_code,
        "ssl_days": ssl_days,
        "audited_at": now.strftime("%Y-%m-%d"),
        "trial_expires": expires,
        "active": activate,
    })
    save_json(LEADS_FILE, leads)

    sites = load_json(SITES_FILE)
    if activate:
        sites = [x for x in sites if x.get("url") != url]
        sites.append({"client_name": name, "url": url, "trial_expires": expires})
        save_json(SITES_FILE, sites)

    synced = git_sync(f"chore(leads): {'activate' if activate else 'audit'} {name}")
    total_audited = len(leads)
    total_active = len(sites)

    mode = "ACTIVATED (10-Day Trial)" if activate else "AUDITED (Lead)"
    tg_msg = (
        f"[{mode}] {name}\n"
        f"URL: {url}\n"
        f"HTTP: {http_code} | SSL: {ssl_days}d\n"
        f"Trial Ends: {expires}\n"
        f"GitHub Sync: {'OK' if synced else 'FAILED'}\n"
        f"Counts -> Audited: {total_audited} | Active Sites: {total_active}"
    )
    tg_sent = send_telegram_alert(tg_msg)
    print(f"{mode} | {name} | HTTP: {http_code} | SSL: {ssl_days}d | Sync: {synced} | TG: {tg_sent} | Audited: {total_audited} | Active: {total_active}")


if __name__ == "__main__":
    main()
