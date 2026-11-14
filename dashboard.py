import hmac
import html
import ipaddress
import os
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer

from storage import connect_db, init_db, list_sites


def render_dashboard_html(sites: list[dict]) -> str:
    """Render an HTML status table with all dynamic strings escaped against XSS."""
    rows_html = []
    for s in sites:
        client = html.escape(str(s["client_name"]))
        url = html.escape(str(s["url"]))
        is_up = s["last_is_up"]
        badge = "NEW" if is_up is None else ("UP" if is_up == 1 else "DOWN")
        color = "#6b7280" if is_up is None else ("#16a34a" if is_up == 1 else "#dc2626")
        code = "-" if s["last_status_code"] is None else str(int(s["last_status_code"]))
        ssl_days = "-" if s["last_ssl_days"] is None else f"{int(s['last_ssl_days'])} days"
        updated = html.escape(str(s["updated_at"]))
        rows_html.append(
            f"<tr>"
            f"<td>{client}</td>"
            f"<td><a href=\"{url}\" rel=\"noopener noreferrer\">{url}</a></td>"
            f"<td style=\"color:{color};font-weight:bold;\">{badge}</td>"
            f"<td>{code}</td>"
            f"<td>{ssl_days}</td>"
            f"<td>{updated}</td>"
            f"</tr>"
        )

    body_rows = "\n".join(rows_html) if rows_html else "<tr><td colspan='6'>No sites monitored yet.</td></tr>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>bsloopstudio Uptime Monitor</title>
<style>
body {{ font-family: sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #111827; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
th, td {{ border: 1px solid #d1d5db; padding: 0.6rem; text-align: left; font-size: 0.95rem; }}
th {{ background: #f3f4f6; }}
</style>
</head>
<body>
<h1>bsloopstudio Uptime &amp; SSL Status</h1>
<p>Plan: Rs 299 / month (up to 10 websites)</p>
<table>
<thead>
<tr><th>Client</th><th>URL</th><th>Status</th><th>HTTP Code</th><th>SSL Expiry</th><th>Last Updated (UTC)</th></tr>
</thead>
<tbody>
{body_rows}
</tbody>
</table>
</body>
</html>"""


class DashboardServer(ThreadingHTTPServer):
    """Threaded server so slow clients cannot block unrelated dashboard reads."""

    daemon_threads = True
    allow_reuse_address = True


class DashboardHandler(BaseHTTPRequestHandler):
    """Serve a read-only status page with optional bearer-token access control."""

    db_path: str = "uptime.db"
    token: str | None = None

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_response(200, "text/plain; charset=utf-8", "OK")
            return
        if self.path != "/":
            self._send_response(404, "text/plain; charset=utf-8", "Not Found")
            return
        if self.token and not self._authorized():
            self._send_response(
                401,
                "text/plain; charset=utf-8",
                "Unauthorized",
                {"WWW-Authenticate": 'Bearer realm="uptime"'},
            )
            return

        conn = connect_db(self.db_path)
        init_db(conn)
        try:
            sites = list_sites(conn)
        finally:
            conn.close()

        page = render_dashboard_html(sites)
        self._send_response(200, "text/html; charset=utf-8", page)

    def _authorized(self) -> bool:
        scheme, _, value = self.headers.get("Authorization", "").partition(" ")
        return scheme.lower() == "bearer" and hmac.compare_digest(
            value.strip().encode("utf-8"), (self.token or "").encode("utf-8")
        )

    def _send_response(
        self,
        code: int,
        content_type: str,
        body: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'",
        )
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        """Disable noisy stdout logging to save SD card and terminal clutter."""
        return


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def validate_port(port: int | str) -> int:
    """Return a valid TCP port number or raise ValueError."""
    if isinstance(port, bool):
        raise ValueError(f"Invalid port: {port}")
    try:
        value = int(port)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid port: {port}") from exc
    if not (1 <= value <= 65535):
        raise ValueError(f"Invalid port: {port}")
    return value


def run_server(
    host: str = "127.0.0.1",
    port: int | str = 8080,
    db_path: str = "uptime.db",
    token: str | None = None,
) -> None:
    """Start the HTTP server. Non-loopback binds require a bearer token."""
    valid_port = validate_port(port)
    if not token and not _is_loopback(host):
        raise ValueError("UPTIME_DASHBOARD_TOKEN is required for non-loopback binds.")
    DashboardHandler.db_path = db_path
    DashboardHandler.token = token or None
    server = DashboardServer((host, valid_port), DashboardHandler)
    print(f"Serving dashboard on http://{host}:{valid_port} (DB: {db_path})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    db = os.environ.get("UPTIME_DB_PATH", "uptime.db")
    host = os.environ.get("UPTIME_HOST", "127.0.0.1")
    port = os.environ.get("UPTIME_PORT", "8080")
    token = os.environ.get("UPTIME_DASHBOARD_TOKEN") or None
    run_server(host=host, port=port, db_path=db, token=token)
