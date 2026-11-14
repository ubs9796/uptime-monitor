import json
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from notifier import format_alert_message, send_telegram_alert, send_webhook_alert
from storage import (
    add_site,
    connect_db,
    init_db,
    list_sites,
    prune_check_history,
    remove_site,
    update_site_state,
)


@pytest.fixture
def db_conn(tmp_path):
    db_file = str(tmp_path / "test_uptime.db")
    conn = connect_db(db_file)
    init_db(conn)
    yield conn
    conn.close()


def test_add_and_list_sites_happy_path(db_conn) -> None:
    site_id = add_site(db_conn, "Apollo Clinic Hyd", "https://example.com")
    sites = list_sites(db_conn)
    assert site_id == 1
    assert len(sites) == 1
    assert sites[0]["client_name"] == "Apollo Clinic Hyd"


def test_add_site_rejects_duplicate_and_empty_name(db_conn) -> None:
    add_site(db_conn, "Client A", "https://example.com")
    with pytest.raises(sqlite3.IntegrityError):
        add_site(db_conn, "Client B", "https://example.com")
    with pytest.raises(ValueError):
        add_site(db_conn, "   ", "https://other.com")


def test_update_site_state_skips_unchanged_write(db_conn) -> None:
    site_id = add_site(db_conn, "Client A", "https://example.com")
    first_write = update_site_state(db_conn, site_id, True, 200, 45, False)
    second_write = update_site_state(db_conn, site_id, True, 200, 44, False)
    third_write = update_site_state(db_conn, site_id, False, 503, 44, False)

    assert first_write is True
    assert second_write is False
    assert third_write is True


def test_update_site_state_unknown_id_raises(db_conn) -> None:
    with pytest.raises(ValueError):
        update_site_state(db_conn, 999, True, 200, 30, False)


def test_update_site_state_records_every_check(db_conn) -> None:
    site_id = add_site(db_conn, "Client A", "https://example.com")
    update_site_state(db_conn, site_id, True, 200, 45, False)
    update_site_state(db_conn, site_id, False, 503, 44, False)

    rows = db_conn.execute(
        "SELECT status_code FROM checks WHERE site_id = ? ORDER BY id ASC;", (site_id,)
    ).fetchall()
    assert [row["status_code"] for row in rows] == [200, 503]


def test_connection_uses_secure_delete(db_conn) -> None:
    assert db_conn.execute("PRAGMA secure_delete;").fetchone()[0] == 1


def test_remove_site_deletes_history(db_conn) -> None:
    site_id = add_site(db_conn, "Client A", "https://example.com")
    update_site_state(db_conn, site_id, True, 200, 45, False)

    assert remove_site(db_conn, "https://example.com") is True
    assert list_sites(db_conn) == []
    history = db_conn.execute(
        "SELECT COUNT(*) FROM checks WHERE site_id = ?;", (site_id,)
    ).fetchone()[0]
    assert history == 0
    assert remove_site(db_conn, "https://example.com") is False


def test_format_alert_message_includes_ssl_warning() -> None:
    msg = format_alert_message("Hyd School", "https://school.in", False, 500, 7)
    assert "[DOWN] Hyd School" in msg
    assert "SSL Warning: 7 days left" in msg


def test_send_webhook_alert_returns_false_without_env(monkeypatch) -> None:
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert send_webhook_alert("Test alert") is False


def test_send_webhook_alert_posts_json(monkeypatch) -> None:
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.com/notify")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert send_webhook_alert("Site down") is True


def test_send_webhook_alert_rejects_plain_http(monkeypatch) -> None:
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "http://hooks.example.com/notify")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert send_webhook_alert("Site down") is False


def test_send_telegram_alert_posts_json(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:ABC-DEF")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        assert send_telegram_alert("Hyderabad Clinic DOWN") is True
        called_req = mock_open.call_args[0][0]
        assert called_req.full_url == "https://api.telegram.org/bot123456:ABC-DEF/sendMessage"
        assert json.loads(called_req.data)["chat_id"] == "987654321"


def test_send_telegram_alert_returns_false_without_env(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert send_telegram_alert("No creds") is False


def _insert_check(conn: sqlite3.Connection, site_id: int, checked_at: str) -> None:
    conn.execute(
        "INSERT INTO checks (site_id, is_up, status_code, ssl_days, checked_at) "
        "VALUES (?, ?, ?, ?, ?);",
        (site_id, 1, 200, 30, checked_at),
    )
    conn.commit()


def test_prune_check_history_keeps_exact_cutoff_and_newer_rows(db_conn) -> None:
    site_id = add_site(db_conn, "Client A", "https://example.com")
    now = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)
    older = (now - timedelta(days=31)).isoformat()
    cutoff = (now - timedelta(days=10)).isoformat()
    newer = (now - timedelta(days=9, hours=23)).isoformat()
    _insert_check(db_conn, site_id, older)
    _insert_check(db_conn, site_id, cutoff)
    _insert_check(db_conn, site_id, newer)

    deleted = prune_check_history(db_conn, 10, now=now)

    assert deleted == 1
    remaining = db_conn.execute(
        "SELECT checked_at FROM checks WHERE site_id = ? ORDER BY checked_at;", (site_id,)
    ).fetchall()
    assert [row["checked_at"] for row in remaining] == [cutoff, newer]


def test_prune_check_history_empty_table_returns_zero(db_conn) -> None:
    assert prune_check_history(db_conn, 30) == 0


@pytest.mark.parametrize("days", [0, -1, True, 1.5, "10"])
def test_prune_check_history_rejects_invalid_days(db_conn, days: object) -> None:
    with pytest.raises(ValueError):
        prune_check_history(db_conn, days)


def test_init_db_creates_checked_at_index(db_conn) -> None:
    indexes = {
        row["name"]
        for row in db_conn.execute("PRAGMA index_list('checks');").fetchall()
    }
    assert "idx_checks_checked_at" in indexes
