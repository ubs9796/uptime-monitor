import threading
import urllib.error
import urllib.request

import pytest

from dashboard import (
    DashboardHandler,
    DashboardServer,
    _is_loopback,
    render_dashboard_html,
    run_server,
    validate_port,
)
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
    server = DashboardServer(("127.0.0.1", 0), DashboardHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
            body = resp.read().decode("utf-8")
            assert resp.getcode() == 200
            assert "Miyapur Dental" in body
            assert "60 days" in body
            assert resp.headers["Cache-Control"] == "no-store"
            assert "default-src 'none'" in resp.headers["Content-Security-Policy"]

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health") as resp:
            assert resp.getcode() == 200
            assert resp.read().decode("utf-8") == "OK"

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/unknown")
        assert exc_info.value.code == 404
    finally:
        server.shutdown()
        server.server_close()


def test_dashboard_requires_bearer_token(tmp_path) -> None:
    db_file = str(tmp_path / "auth.db")
    conn = connect_db(db_file)
    init_db(conn)
    add_site(conn, "Auth Clinic", "https://auth.example.in")
    conn.close()

    DashboardHandler.db_path = db_file
    DashboardHandler.token = "s3cret-token"
    server = DashboardServer(("127.0.0.1", 0), DashboardHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"

    try:
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(f"{base}/")
        assert exc_info.value.code == 401

        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(
                urllib.request.Request(f"{base}/", headers={"Authorization": "Bearer wrong"})
            )
        assert exc_info.value.code == 401

        allowed = urllib.request.Request(
            f"{base}/", headers={"Authorization": "Bearer s3cret-token"}
        )
        with urllib.request.urlopen(allowed) as resp:
            assert resp.getcode() == 200
            assert "Auth Clinic" in resp.read().decode("utf-8")

        with urllib.request.urlopen(f"{base}/health") as resp:
            assert resp.getcode() == 200
    finally:
        DashboardHandler.token = None
        server.shutdown()
        server.server_close()


def test_run_server_rejects_invalid_port() -> None:
    with pytest.raises(ValueError):
        run_server(port=70000)


def test_run_server_requires_token_for_non_loopback() -> None:
    with pytest.raises(ValueError):
        run_server(host="0.0.0.0", port=8080)


def test_is_loopback_detection() -> None:
    assert _is_loopback("127.0.0.1")
    assert _is_loopback("::1")
    assert _is_loopback("localhost")
    assert not _is_loopback("0.0.0.0")
    assert not _is_loopback("example.com")


def test_dashboard_server_handles_requests_concurrently(tmp_path, monkeypatch) -> None:
    db_file = str(tmp_path / "threaded.db")
    conn = connect_db(db_file)
    init_db(conn)
    conn.close()

    started = threading.Event()
    release = threading.Event()

    def slow_list_sites(_conn) -> list[dict]:
        started.set()
        release.wait(timeout=2)
        return []

    monkeypatch.setattr("dashboard.list_sites", slow_list_sites)
    DashboardHandler.db_path = db_file
    DashboardHandler.token = None
    server = DashboardServer(("127.0.0.1", 0), DashboardHandler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"

    slow_request = threading.Thread(
        target=lambda: urllib.request.urlopen(f"{base}/", timeout=3).read(),
        daemon=True,
    )
    slow_request.start()

    try:
        assert started.wait(timeout=2)
        with urllib.request.urlopen(f"{base}/health", timeout=1) as resp:
            assert resp.getcode() == 200
            assert resp.read().decode("utf-8") == "OK"
    finally:
        release.set()
        slow_request.join(timeout=2)
        server.shutdown()
        server.server_close()


def test_dashboard_server_uses_daemon_threads() -> None:
    assert DashboardServer.daemon_threads is True


@pytest.mark.parametrize("port", [0, 70000, -1, "not-a-port", True])
def test_validate_port_rejects_invalid_values(port: object) -> None:
    with pytest.raises(ValueError):
        validate_port(port)


def test_validate_port_accepts_boundaries() -> None:
    assert validate_port(1) == 1
    assert validate_port("65535") == 65535
