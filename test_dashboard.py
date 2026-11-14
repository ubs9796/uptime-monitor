import threading
import urllib.error
import urllib.request

import pytest

from dashboard import DashboardHandler, HTTPServer, render_dashboard_html, run_server
from storage import add_site, connect_db, init_db, update_site_state


def test_render_dashboard_html_escapes_xss() -> None:
    malicious_sites = [
        {
            "id": 1,
            "client_name": "<script>alert(1)</script>",
            "url": "https://example.com/\"><script>",
            "last_is_up": 1,
            "last_status_code": 200,
            "last_ssl_days": 30,
            "ssl_alert_sent": 0,
            "updated_at": "2026-11-14T00:00:00Z",
        }
    ]
    output = render_dashboard_html(malicious_sites)
    assert "<script>alert(1)</script>" not in output
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in output
    assert "UP" in output


def test_render_dashboard_html_empty_state() -> None:
    output = render_dashboard_html([])
    assert "No sites monitored yet." in output


def test_dashboard_http_routes(tmp_path) -> None:
    db_file = str(tmp_path / "web.db")
    conn = connect_db(db_file)
    init_db(conn)
    site_id = add_site(conn, "Miyapur Dental", "https://dental.example.in")
    update_site_state(conn, site_id, True, 200, 60, False)
    conn.close()

    DashboardHandler.db_path = db_file
    server = HTTPServer(("127.0.0.1", 0), DashboardHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
            body = resp.read().decode("utf-8")
            assert resp.getcode() == 200
            assert "Miyapur Dental" in body
            assert "60 days" in body

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health") as resp:
            assert resp.getcode() == 200
            assert resp.read().decode("utf-8") == "OK"

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/unknown")
        assert exc_info.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_run_server_rejects_invalid_port() -> None:
    with pytest.raises(ValueError):
        run_server(port=70000)
