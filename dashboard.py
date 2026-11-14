import html
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

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


class DashboardHandler(BaseHTTPRequestHandler):
    """Serve read-only status page on GET / and health check on GET /health."""

    db_path: str = "uptime.db"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_response(200, "text/plain; charset=utf-8", "OK")
            return
        if self.path != "/":
            self._send_response(404, "text/plain; charset=utf-8", "Not Found")
            return

        conn = connect_db(self.db_path)
        init_db(conn)
        try:
            sites = list_sites(conn)
        finally:
            conn.close()

        page = render_dashboard_html(sites)
        self._send_response(200, "text/html; charset=utf-8", page)

    def _send_response(self, code: int, content_type: str, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        """Disable noisy stdout logging to save SD card and terminal clutter."""
        return


def run_server(host: str = "127.0.0.1", port: int = 8080, db_path: str = "uptime.db") -> None:
    """Start the HTTP server."""
    if not (1 <= int(port) <= 65535):
        raise ValueError(f"Invalid port: {port}")
    DashboardHandler.db_path = db_path
    server = HTTPServer((host, int(port)), DashboardHandler)
    print(f"Serving dashboard on http://{host}:{port} (DB: {db_path})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    db = os.environ.get("UPTIME_DB_PATH", "uptime.db")
    host = os.environ.get("UPTIME_HOST", "127.0.0.1")
    port = int(os.environ.get("UPTIME_PORT", "8080"))
    run_server(host=host, port=port, db_path=db)
