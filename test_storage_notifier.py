import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from notifier import format_alert_message, send_webhook_alert
from storage import add_site, connect_db, init_db, list_sites, update_site_state


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


def test_format_alert_message_includes_ssl_warning() -> None:
    msg = format_alert_message("Hyd School", "https://school.in", False, 500, 7)
    assert "[DOWN] Hyd School" in msg
    assert "SSL Warning: 7 days left" in msg


def test_send_webhook_alert_returns_false_without_env(monkeypatch) -> None:
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    assert send_webhook_alert("Test alert") is False


def test_send_webhook_alert_posts_json(monkeypatch) -> None:
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.example.com/notify")
    mock_resp = MagicMock()
    mock_resp.getcode.return_value = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert send_webhook_alert("Site down") is True
