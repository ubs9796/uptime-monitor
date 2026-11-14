import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from checker import validate_url


def connect_db(db_path: str = "uptime.db") -> sqlite3.Connection:
    """Open SQLite with WAL, foreign keys, and secure deletion enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA secure_delete=ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the state and check-history tables if they do not exist."""
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER NOT NULL,
            is_up INTEGER NOT NULL,
            status_code INTEGER,
            ssl_days INTEGER,
            checked_at TEXT NOT NULL,
            FOREIGN KEY (site_id) REFERENCES monitored_sites (id) ON DELETE CASCADE
        );
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_checks_site_id ON checks (site_id, id);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_checks_checked_at ON checks (checked_at);"
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


def remove_site(conn: sqlite3.Connection, url: str) -> bool:
    """Delete a monitored site and its history. Returns True if a row was removed."""
    clean_url = validate_url(url)
    row = conn.execute(
        "SELECT id FROM monitored_sites WHERE url = ?;", (clean_url,)
    ).fetchone()
    if row is None:
        return False
    conn.execute("DELETE FROM monitored_sites WHERE id = ?;", (row["id"],))
    conn.commit()
    return True


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
    """Record a check in history and update state only when it changes.

    The current-state row is written only on transitions to protect the Pi 3B
    SD card, while every check is appended to the ``checks`` history table.
    """
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

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO checks (site_id, is_up, status_code, ssl_days, checked_at)
        VALUES (?, ?, ?, ?, ?);
        """,
        (site_id, new_up, status_code, ssl_days, now),
    )
    if changed:
        conn.execute(
            """
            UPDATE monitored_sites
            SET last_is_up = ?, last_status_code = ?, last_ssl_days = ?, ssl_alert_sent = ?, updated_at = ?
            WHERE id = ?;
            """,
            (new_up, status_code, ssl_days, new_ssl_alert, now, site_id),
        )
    conn.commit()
    return changed


def prune_check_history(
    conn: sqlite3.Connection,
    days: int,
    now: datetime | None = None,
) -> int:
    """Delete history rows strictly older than ``days`` and return the count.

    Rows exactly at the cutoff are kept. Callers must opt in explicitly; no
    automatic retention runs during a normal check cycle.
    """
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise ValueError("days must be an integer greater than or equal to 1.")
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    cur = conn.execute("DELETE FROM checks WHERE checked_at < ?;", (cutoff.isoformat(),))
    conn.commit()
    return int(cur.rowcount)
