import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from checker import validate_url


def connect_db(db_path: str = "uptime.db") -> sqlite3.Connection:
    """Open SQLite connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create monitored_sites table if it does not exist."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS monitored_sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            last_is_up INTEGER,
            last_status_code INTEGER,
            last_ssl_days INTEGER,
            ssl_alert_sent INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.commit()


def add_site(conn: sqlite3.Connection, client_name: str, url: str) -> int:
    """Validate and insert a customer site. Returns new row ID."""
    if not isinstance(client_name, str) or not client_name.strip():
        raise ValueError("Client name must be a non-empty string.")
    clean_url = validate_url(url)
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        """
        INSERT INTO monitored_sites (client_name, url, updated_at)
        VALUES (?, ?, ?)
        """,
        (client_name.strip(), clean_url, now),
    )
    conn.commit()
    return int(cur.lastrowid)


def list_sites(conn: sqlite3.Connection) -> list[dict]:
    """Return all monitored sites as plain dicts."""
    rows = conn.execute("SELECT * FROM monitored_sites ORDER BY id ASC;").fetchall()
    return [dict(row) for row in rows]


def update_site_state(
    conn: sqlite3.Connection,
    site_id: int,
    is_up: bool,
    status_code: int,
    ssl_days: Optional[int],
    ssl_alert_sent: bool,
) -> bool:
    """Write to disk only when state changes to protect Pi 3B SD card."""
    row = conn.execute(
        "SELECT last_is_up, last_status_code, ssl_alert_sent FROM monitored_sites WHERE id = ?;",
        (site_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"Site ID {site_id} not found.")

    new_up = 1 if is_up else 0
    new_ssl_alert = 1 if ssl_alert_sent else 0
    changed = (
        row["last_is_up"] != new_up
        or row["last_status_code"] != status_code
        or row["ssl_alert_sent"] != new_ssl_alert
    )
    if not changed:
        return False

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        UPDATE monitored_sites
        SET last_is_up = ?, last_status_code = ?, last_ssl_days = ?, ssl_alert_sent = ?, updated_at = ?
        WHERE id = ?;
        """,
        (new_up, status_code, ssl_days, new_ssl_alert, now, site_id),
    )
    conn.commit()
    return True
