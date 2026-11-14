import json
import threading
from unittest.mock import patch

import pytest

from runner import main, resolve_check_workers, run_check_cycle
from storage import add_site, connect_db, init_db


def test_run_check_cycle_skips_when_internet_offline(tmp_path) -> None:
    db_file = str(tmp_path / "offline.db")
    with patch("runner.is_internet_online", return_value=False):
        result = run_check_cycle(db_path=db_file)
    assert result == {"checked": 0, "changed": 0, "alerts_sent": 0, "skipped_offline": 1}


def test_run_check_cycle_alerts_once_on_state_change(tmp_path) -> None:
    db_file = str(tmp_path / "monitor.db")
    conn = connect_db(db_file)
    init_db(conn)
    add_site(conn, "Hyderabad Clinic", "https://clinic.example.in")
    conn.close()

    with (
        patch("runner.is_internet_online", return_value=True),
        patch("runner.check_http_status", return_value=(False, 503)),
        patch("runner.get_ssl_days_left", return_value=10),
        patch("runner.send_webhook_alert", return_value=True) as mock_alert,
    ):
        first = run_check_cycle(db_path=db_file, ssl_warn_days=14)
        second = run_check_cycle(db_path=db_file, ssl_warn_days=14)

    assert first == {"checked": 1, "changed": 1, "alerts_sent": 1, "skipped_offline": 0}
    assert second == {"checked": 1, "changed": 0, "alerts_sent": 0, "skipped_offline": 0}
    assert mock_alert.call_count == 1


def test_cli_add_and_list_commands(tmp_path, capsys) -> None:
    db_file = str(tmp_path / "cli.db")
    rc_add = main(["--db", db_file, "add", "Test Shop", "https://shop.example.com"])
    rc_list = main(["--db", db_file, "list"])
    captured = capsys.readouterr().out

    assert rc_add == 0
    assert rc_list == 0
    assert "Added site #1: Test Shop" in captured
    assert "Test Shop | https://shop.example.com | NEW" in captured


def test_cli_remove_and_list_json(tmp_path, capsys) -> None:
    db_file = str(tmp_path / "cli_json.db")
    assert main(["--db", db_file, "add", "Test Shop", "https://shop.example.com"]) == 0
    capsys.readouterr()

    assert main(["--db", db_file, "list", "--json"]) == 0
    sites = json.loads(capsys.readouterr().out)
    assert [site["client_name"] for site in sites] == ["Test Shop"]

    assert main(["--db", db_file, "remove", "https://shop.example.com"]) == 0
    assert "Removed site" in capsys.readouterr().out

    assert main(["--db", db_file, "list", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []

    assert main(["--db", db_file, "remove", "https://missing.example.com"]) == 1
    assert "Site not found" in capsys.readouterr().err


def test_resolve_check_workers_defaults_and_boundaries(monkeypatch) -> None:
    monkeypatch.delenv("UPTIME_CHECK_WORKERS", raising=False)
    assert resolve_check_workers() == 4
    assert resolve_check_workers(1) == 1
    assert resolve_check_workers(32) == 32

    for invalid in (0, 33, -1, True, 1.5):
        with pytest.raises(ValueError):
            resolve_check_workers(invalid)

    monkeypatch.setenv("UPTIME_CHECK_WORKERS", "8")
    assert resolve_check_workers() == 8
    monkeypatch.setenv("UPTIME_CHECK_WORKERS", "many")
    with pytest.raises(ValueError):
        resolve_check_workers()


def test_run_check_cycle_rejects_invalid_workers_before_network(tmp_path) -> None:
    with patch("runner.is_internet_online") as mock_probe:
        with pytest.raises(ValueError):
            run_check_cycle(db_path=str(tmp_path / "invalid.db"), workers=0)
    mock_probe.assert_not_called()


def test_run_check_cycle_checks_sites_concurrently(tmp_path) -> None:
    db_file = str(tmp_path / "concurrent.db")
    conn = connect_db(db_file)
    init_db(conn)
    add_site(conn, "Site A", "http://a.example.com")
    add_site(conn, "Site B", "http://b.example.com")
    conn.close()

    barrier = threading.Barrier(2)

    def fake_check(url: str, timeout_sec: float = 5.0) -> tuple[bool, int]:
        barrier.wait(timeout=2)
        return (True, 200)

    with (
        patch("runner.is_internet_online", return_value=True),
        patch("runner.check_http_status", side_effect=fake_check),
        patch("runner.send_webhook_alert", return_value=False),
    ):
        result = run_check_cycle(db_path=db_file, workers=2)

    assert result == {"checked": 2, "changed": 2, "alerts_sent": 0, "skipped_offline": 0}


def test_run_check_cycle_records_network_failures_with_workers(tmp_path) -> None:
    db_file = str(tmp_path / "failures.db")
    conn = connect_db(db_file)
    init_db(conn)
    add_site(conn, "Site A", "http://a.example.com")
    add_site(conn, "Site B", "http://b.example.com")
    conn.close()

    with (
        patch("runner.is_internet_online", return_value=True),
        patch("runner.check_http_status", return_value=(False, 0)),
        patch("runner.send_webhook_alert", return_value=False),
    ):
        result = run_check_cycle(db_path=db_file, workers=2)

    assert result == {"checked": 2, "changed": 2, "alerts_sent": 0, "skipped_offline": 0}
    conn = connect_db(db_file)
    try:
        rows = conn.execute("SELECT is_up, status_code FROM checks ORDER BY id;").fetchall()
    finally:
        conn.close()
    assert [(row["is_up"], row["status_code"]) for row in rows] == [(0, 0), (0, 0)]


def test_cli_prune_deletes_old_history(tmp_path, capsys) -> None:
    db_file = str(tmp_path / "prune_cli.db")
    assert main(["--db", db_file, "add", "Test Shop", "https://shop.example.com"]) == 0
    capsys.readouterr()

    conn = connect_db(db_file)
    try:
        conn.execute(
            "INSERT INTO checks (site_id, is_up, status_code, ssl_days, checked_at) "
            "VALUES (1, 1, 200, 30, '2000-01-01T00:00:00+00:00');"
        )
        conn.commit()
    finally:
        conn.close()

    assert main(["--db", db_file, "prune", "--days", "30"]) == 0
    assert "Pruned 1 check-history row(s) older than 30 day(s)." in capsys.readouterr().out


def test_cli_prune_rejects_invalid_days(tmp_path, capsys) -> None:
    db_file = str(tmp_path / "prune_invalid.db")
    assert main(["--db", db_file, "prune", "--days", "0"]) == 2
    assert "days must be an integer" in capsys.readouterr().err
