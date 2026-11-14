import json
from unittest.mock import patch

from runner import main, run_check_cycle
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
